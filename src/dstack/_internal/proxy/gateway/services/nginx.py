import importlib.resources
import subprocess
import tempfile
from asyncio import Lock
from pathlib import Path
from typing import Optional

import jinja2
from pydantic import BaseModel
from typing_extensions import Literal

from dstack._internal.core.models.routers import AnyRouterConfig
from dstack._internal.proxy.gateway.const import PROXY_PORT_ON_GATEWAY
from dstack._internal.proxy.gateway.model_routers import (
    Router,
    RouterContext,
    get_router,
)
from dstack._internal.proxy.gateway.models import ACMESettings
from dstack._internal.proxy.lib.errors import ProxyError, UnexpectedProxyError
from dstack._internal.utils.common import run_async
from dstack._internal.utils.logging import get_logger

CERTBOT_TIMEOUT = 40
CERTBOT_2ND_TIMEOUT = 5
CONFIGS_DIR = Path("/etc/nginx/sites-enabled")
logger = get_logger(__name__)


class SiteConfig(BaseModel):
    type: str
    domain: str
    https: bool = True

    def render(self) -> str:
        template = read_package_resource(f"{self.type}.jinja2")
        return jinja2.Template(template).render(
            **self.dict(),
            proxy_port=PROXY_PORT_ON_GATEWAY,
        )


class ReplicaConfig(BaseModel):
    id: str
    socket: Path


class LimitReqZoneConfig(BaseModel):
    name: str
    key: str
    rpm: int


class LimitReqConfig(BaseModel):
    zone: str
    burst: int


class LocationConfig(BaseModel):
    prefix: str
    limit_req: Optional[LimitReqConfig]


class ServiceConfig(SiteConfig):
    type: Literal["service"] = "service"
    project_name: str
    auth: bool
    client_max_body_size: int
    access_log_path: Path
    limit_req_zones: list[LimitReqZoneConfig]
    locations: list[LocationConfig]
    replicas: list[ReplicaConfig]
    router_config: Optional[AnyRouterConfig] = None
    model_id: Optional[str] = None


class ModelEntrypointConfig(SiteConfig):
    type: Literal["entrypoint"] = "entrypoint"
    project_name: str


class Nginx:
    """Updates nginx config and issues SSL certificates."""

    def __init__(self, conf_dir: Path = Path("/etc/nginx/sites-enabled")) -> None:
        self._conf_dir = conf_dir
        self._lock: Lock = Lock()
        self._router: Optional[Router] = None

    async def register(self, conf: SiteConfig, acme: ACMESettings) -> None:
        logger.debug("Registering %s domain %s", conf.type, conf.domain)
        conf_name = self.get_config_name(conf.domain)
        async with self._lock:
            if conf.https:
                await run_async(self.run_certbot, conf.domain, acme)
            await run_async(self.write_conf, conf.render(), conf_name)

            if isinstance(conf, ServiceConfig) and conf.router_config and conf.model_id:
                if self._router is None:
                    ctx = RouterContext(
                        host="127.0.0.1",
                        port=3000,
                        log_dir=Path("./router_logs"),
                        log_level="info",
                    )
                    self._router = get_router(conf.router_config, context=ctx)
                    if not await run_async(self._router.is_running):
                        await run_async(self._router.start)

                replicas = await run_async(
                    self._router.register_replicas,
                    conf.domain,
                    len(conf.replicas),
                    conf.model_id,
                )

                allocated_ports = [int(r.url.rsplit(":", 1)[-1]) for r in replicas]
                try:
                    await run_async(self.write_router_workers_conf, conf, allocated_ports)
                except Exception as e:
                    logger.exception(
                        "write_router_workers_conf failed for domain=%s: %s", conf.domain, e
                    )
                    raise
                finally:
                    # Always update router state, regardless of nginx reload status
                    await run_async(self._router.update_replicas, replicas)

        logger.info("Registered %s domain %s", conf.type, conf.domain)

    async def unregister(self, domain: str) -> None:
        logger.debug("Unregistering domain %s", domain)
        conf_path = self._conf_dir / self.get_config_name(domain)
        if not conf_path.exists():
            return
        async with self._lock:
            await run_async(sudo_rm, conf_path)
            # Generic router implementation
            if self._router is not None:
                # Unregister replicas for this domain (router handles domain-to-model_id lookup)
                await run_async(self._router.unregister_replicas, domain)

                # Remove workers config file (router-specific naming)
                workers_conf_path = self._conf_dir / f"router-workers.{domain}.conf"
                if workers_conf_path.exists():
                    await run_async(sudo_rm, workers_conf_path)

            await run_async(self.reload)
        logger.info("Unregistered domain %s", domain)

    @staticmethod
    def reload() -> None:
        cmd = ["sudo", "systemctl", "reload", "nginx.service"]
        r = subprocess.run(cmd, timeout=10)
        if r.returncode != 0:
            raise UnexpectedProxyError("Failed to reload nginx")

    def write_conf(self, conf: str, conf_name: str) -> None:
        """Update config and reload nginx. Rollback changes on error."""
        conf_path = self._conf_dir / conf_name
        old_conf = conf_path.read_text() if conf_path.exists() else None
        if conf == old_conf:
            return
        sudo_write(conf_path, conf)
        try:
            self.reload()
        except UnexpectedProxyError:
            # rollback changes
            if old_conf is not None:
                sudo_write(conf_path, old_conf)
            else:
                sudo_rm(conf_path)
            raise

    @classmethod
    def run_certbot(cls, domain: str, acme: ACMESettings) -> None:
        if cls.certificate_exists(domain):
            return

        logger.info("Running certbot for %s", domain)

        cmd = ["sudo", "timeout", "--kill-after", str(CERTBOT_2ND_TIMEOUT), str(CERTBOT_TIMEOUT)]
        cmd += ["certbot", "certonly"]
        cmd += ["--non-interactive", "--agree-tos", "--register-unsafely-without-email"]
        cmd += ["--keep", "--nginx", "--domain", domain]

        if acme.server:
            cmd += ["--server", str(acme.server)]

        if acme.eab_kid and acme.eab_hmac_key:
            cmd += ["--eab-kid", acme.eab_kid]
            cmd += ["--eab-hmac-key", acme.eab_hmac_key]

        r = subprocess.run(
            cmd,
            capture_output=True,
            timeout=CERTBOT_TIMEOUT + CERTBOT_2ND_TIMEOUT + 1,  # shouldn't happen
        )
        if r.returncode == 124:
            raise ProxyError(
                f"Could not obtain {domain} TLS certificate in {CERTBOT_TIMEOUT}s."
                " Make sure DNS records are configured for this gateway."
            )
        if r.returncode != 0:
            raise ProxyError(f"Error obtaining {domain} TLS certificate:\n{r.stderr.decode()}")

    @staticmethod
    def certificate_exists(domain: str) -> bool:
        cmd = ["sudo", "test", "-e", f"/etc/letsencrypt/live/{domain}/fullchain.pem"]
        return subprocess.run(cmd, timeout=2).returncode == 0

    @staticmethod
    def get_config_name(domain: str) -> str:
        return f"443-{domain}.conf"

    def write_global_conf(self) -> None:
        conf = read_package_resource("00-log-format.conf")
        self.write_conf(conf, "00-log-format.conf")

    def write_router_workers_conf(self, conf: ServiceConfig, allocated_ports: list[int]) -> None:
        """Write router workers configuration file (generic)."""
        # Pass ports to template
        workers_config = generate_router_workers_config(conf, allocated_ports)
        workers_conf_name = f"router-workers.{conf.domain}.conf"
        workers_conf_path = self._conf_dir / workers_conf_name
        sudo_write(workers_conf_path, workers_config)
        self.reload()


def generate_router_workers_config(conf: ServiceConfig, allocated_ports: list[int]) -> str:
    """Generate router workers configuration (generic, uses sglang_workers.jinja2 template)."""
    template = read_package_resource("sglang_workers.jinja2")
    return jinja2.Template(template).render(
        replicas=conf.replicas,
        ports=allocated_ports,
        proxy_port=PROXY_PORT_ON_GATEWAY,
    )


def read_package_resource(file: str) -> str:
    return (
        importlib.resources.files("dstack._internal.proxy.gateway")
        .joinpath(f"resources/nginx/{file}")
        .read_text()
    )


def sudo_write(path: Path, content: str) -> None:
    with tempfile.NamedTemporaryFile("w") as temp:
        temp.write(content)
        temp.flush()
        temp.seek(0)
        r = subprocess.run(sudo() + ["cp", "-p", temp.name, path], timeout=3)
        if r.returncode != 0:
            raise UnexpectedProxyError("Failed to copy file as sudo")


def sudo_rm(path: Path) -> None:
    r = subprocess.run(sudo() + ["rm", path], timeout=3)
    if r.returncode != 0:
        raise UnexpectedProxyError("Failed to remove file as sudo")


def sudo() -> list[str]:
    """Mocked in tests"""
    return ["sudo"]
