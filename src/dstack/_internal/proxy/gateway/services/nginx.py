import importlib.resources
import subprocess
import tempfile
from asyncio import Lock
from pathlib import Path
from typing import Optional

import jinja2
from pydantic import BaseModel
from typing_extensions import Literal

from dstack._internal.proxy.gateway.const import PROXY_PORT_ON_GATEWAY
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
    router: Optional[str] = None


class ModelEntrypointConfig(SiteConfig):
    type: Literal["entrypoint"] = "entrypoint"
    project_name: str


class Nginx:
    """Updates nginx config and issues SSL certificates."""

    def __init__(self, conf_dir: Path = Path("/etc/nginx/sites-enabled")) -> None:
        self._conf_dir = conf_dir
        self._lock: Lock = Lock()

    async def register(self, conf: SiteConfig, acme: ACMESettings) -> None:
        logger.debug("Registering %s domain %s", conf.type, conf.domain)
        conf_name = self.get_config_name(conf.domain)
        logger.debug(f"[SglangRouterTesting] Register Conf object dict: {conf.dict()}")
        async with self._lock:
            if conf.https:
                await run_async(self.run_certbot, conf.domain, acme)
            await run_async(self.write_conf, conf.render(), conf_name)
            # Start sglang-router if router is sglang
            if hasattr(conf, "router") and conf.router == "sglang":
                replicas = len(conf.replicas) if hasattr(conf, "replicas") and conf.replicas else 1
                logger.debug(
                    f"[SglangRouterTesting] Starting sglang-router with {replicas} replicas"
                )
                await run_async(self.write_sglang_workers_conf, conf)
                await run_async(self.start_sglang_router, replicas)

        logger.info("Registered %s domain %s", conf.type, conf.domain)

    async def unregister(self, domain: str) -> None:
        logger.debug("Unregistering domain %s", domain)
        conf_path = self._conf_dir / self.get_config_name(domain)
        if not conf_path.exists():
            return
        async with self._lock:
            await run_async(sudo_rm, conf_path)
            await run_async(self.reload)
        logger.info("Unregistered domain %s", domain)

    @staticmethod
    def reload() -> None:
        cmd = ["sudo", "systemctl", "reload", "nginx.service"]
        r = subprocess.run(cmd, timeout=10)
        if r.returncode != 0:
            raise UnexpectedProxyError("Failed to reload nginx")

    @staticmethod
    def start_sglang_router(replicas: int) -> None:
        """Start sglang-router service, killing existing one if running."""
        try:
            # Kill existing sglang-router if running
            result = subprocess.run(
                ["pgrep", "-f", "sglang_router.launch_router"], capture_output=True, timeout=5
            )
            if result.returncode == 0:
                logger.info("Killing existing sglang-router...")
                subprocess.run(["pkill", "-f", "sglang_router.launch_router"], timeout=5)
                # Wait a moment for the process to terminate
                import time

                time.sleep(1)

            # Generate worker URLs based on replica count
            worker_urls = []
            for i in range(1, replicas + 1):
                worker_urls.append(f"http://127.0.0.1:{10000 + i}")

            # Start sglang-router with system-wide installation
            logger.info(f"Starting sglang-router with {replicas} replicas...")
            cmd = (
                [
                    "python3",
                    "-m",
                    "sglang_router.launch_router",  # Use system python3
                    "--worker-urls",
                ]
                + worker_urls
                + [
                    "--host",
                    "0.0.0.0",
                    "--port",
                    "3000",
                    "--log-level",
                    "debug",
                    "--log-dir",
                    "./router_logs",
                ]
            )
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        except Exception as e:
            logger.error(f"Failed to start sglang-router: {e}")

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

    def write_sglang_workers_conf(self, conf: SiteConfig) -> None:
        workers_config = generate_sglang_workers_config(conf)
        workers_conf_name = f"sglang-workers.{conf.domain}.conf"
        workers_conf_path = self._conf_dir / workers_conf_name
        sudo_write(workers_conf_path, workers_config)
        self.reload()


def generate_sglang_workers_config(conf: SiteConfig) -> str:
    template = read_package_resource("sglang_workers.jinja2")
    return jinja2.Template(template).render(
        replicas=conf.replicas,
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
