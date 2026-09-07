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
from dstack._internal.proxy.lib import models
from dstack._internal.proxy.lib.errors import ProxyError, UnexpectedProxyError
from dstack._internal.utils.common import run_async
from dstack._internal.utils.logging import get_logger

CERTBOT_TIMEOUT = 40
CERTBOT_2ND_TIMEOUT = 5
NGINX_DIR = Path("/etc/nginx")
logger = get_logger(__name__)


class SiteConfig(BaseModel):
    type: str
    domain: str
    https: bool = True

    def render(self) -> str:
        template = read_package_resource(f"{self.type}.jinja2")
        render_dict = self.model_dump()
        render_dict["proxy_port"] = PROXY_PORT_ON_GATEWAY
        return jinja2.Template(template).render(**render_dict)


class ReplicaConfig(BaseModel):
    id: str
    socket: Path
    port: int
    internal_ip: Optional[str] = None


class LimitReqZoneConfig(BaseModel):
    name: str
    key: str
    rpm: int


class LimitReqConfig(BaseModel):
    zone: str
    burst: int


class LocationConfig(BaseModel):
    prefix: str
    limit_req: Optional[LimitReqConfig] = None


class ServiceConfig(SiteConfig):
    type: Literal["service"] = "service"
    project_name: str
    auth: bool
    client_max_body_size: int
    access_log_path: Path
    limit_req_zones: list[LimitReqZoneConfig]
    locations: list[LocationConfig]
    replicas: list[ReplicaConfig]
    has_router_replica: bool = False
    cors_enabled: bool = False


class ModelEntrypointConfig(SiteConfig):
    type: Literal["entrypoint"] = "entrypoint"
    project_name: str


class Nginx:
    """Updates nginx config and issues SSL certificates."""

    def __init__(self, nginx_dir: Path = NGINX_DIR) -> None:
        self._nginx_dir = nginx_dir
        self._sites_enabled_dir = nginx_dir / "sites-enabled"
        self._nginx_conf_path = nginx_dir / "nginx.conf"
        self._lock: Lock = Lock()

    async def register(self, conf: SiteConfig, acme: ACMESettings) -> None:
        logger.debug("Registering %s domain %s", conf.type, conf.domain)
        conf_name = self.get_config_name(conf.domain)
        async with self._lock:
            if conf.https:
                await run_async(self.run_certbot, conf.domain, acme)

            await run_async(self.write_conf, conf.render(), self._sites_enabled_dir / conf_name)

        logger.info("Registered %s domain %s", conf.type, conf.domain)

    async def unregister(self, service: models.Service) -> None:
        domain = service.domain_safe
        logger.debug("Unregistering domain %s", domain)
        conf_path = self._sites_enabled_dir / self.get_config_name(domain)
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

    def write_conf(self, conf: str, conf_path: Path) -> None:
        """Update config and reload nginx. Rollback changes on error."""
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
        cmd += ["--non-interactive", "--agree-tos", "--register-unsafely-without-email", "--quiet"]
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
            msg = (
                r.stderr.decode()
                .lstrip("An unexpected error occurred:\n")
                .strip()
                .replace("\n", " ")
            )
            raise ProxyError(f"Error obtaining {domain} TLS certificate: {msg}")

    @staticmethod
    def certificate_exists(domain: str) -> bool:
        cmd = ["sudo", "test", "-e", f"/etc/letsencrypt/live/{domain}/fullchain.pem"]
        return subprocess.run(cmd, timeout=2).returncode == 0

    @staticmethod
    def get_config_name(domain: str) -> str:
        return f"443-{domain}.conf"

    def write_global_conf(self) -> None:
        log_format_conf = read_package_resource("00-log-format.conf")
        self.write_conf(log_format_conf, self._sites_enabled_dir / "00-log-format.conf")

        nginx_conf = read_package_resource("nginx.conf")
        self.write_conf(nginx_conf, self._nginx_conf_path)


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
