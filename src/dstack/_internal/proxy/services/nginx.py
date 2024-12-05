import importlib.resources
import subprocess
import tempfile
from asyncio import Lock
from pathlib import Path

import jinja2
from pydantic import AnyHttpUrl, BaseModel
from typing_extensions import Literal, Optional

from dstack._internal.proxy.errors import ProxyError, UnexpectedProxyError
from dstack._internal.utils.common import run_async
from dstack._internal.utils.logging import get_logger

RESOURCES_PACKAGE = "dstack._internal.proxy.resources.nginx"
CONFIGS_DIR = Path("/etc/nginx/sites-enabled")
PROXY_PORT = 8000
logger = get_logger(__name__)


class SiteConfig(BaseModel):
    type: str
    domain: str
    https: bool = True

    def render(self) -> str:
        template = importlib.resources.read_text(RESOURCES_PACKAGE, f"{self.type}.jinja2")
        return jinja2.Template(template).render(
            **self.dict(),
            proxy_port=PROXY_PORT,
        )


class ReplicaConfig(BaseModel):
    id: str
    socket: Path


class ServiceSiteConfig(SiteConfig):
    type: Literal["service"] = "service"
    project_name: str
    run_name: str
    auth: bool
    client_max_body_size: int
    access_log_path: Path
    replicas: list[ReplicaConfig]


class EntrypointSiteConfig(SiteConfig):
    type: Literal["entrypoint"] = "entrypoint"
    proxy_path: str


class ACMESettings(BaseModel):
    server: Optional[AnyHttpUrl] = None
    eab_kid: Optional[str] = None
    eab_hmac_key: Optional[str] = None


class Nginx:
    """Updates nginx config and issues SSL certificates."""

    def __init__(self) -> None:
        self._acme_settings = ACMESettings()
        self._lock: Lock = Lock()

    async def set_acme_settings(
        self,
        server: Optional[AnyHttpUrl],
        eab_kid: Optional[str],
        eab_hmac_key: Optional[str],
    ) -> None:
        async with self._lock:
            self._acme_settings = ACMESettings(
                server=server, eab_kid=eab_kid, eab_hmac_key=eab_hmac_key
            )

    async def register(self, conf: SiteConfig) -> None:
        logger.debug("Registering %s domain %s", conf.type, conf.domain)
        conf_name = self.get_config_name(conf.domain)

        async with self._lock:
            if conf.https:
                await run_async(self.run_certbot, conf.domain)
            await run_async(self.write_conf, conf.render(), conf_name)

        logger.info("Registered %s domain %s", conf.type, conf.domain)

    async def unregister(self, domain: str) -> None:
        logger.debug("Unregistering domain %s", domain)
        conf_path = CONFIGS_DIR / self.get_config_name(domain)
        if not conf_path.exists():
            return
        async with self._lock:
            await run_async(sudo_rm, conf_path)
            await run_async(self.reload)
        logger.info("Unregistered domain %s", domain)

    @staticmethod
    def reload() -> None:
        cmd = ["sudo", "systemctl", "reload", "nginx.service"]
        r = subprocess.run(cmd)
        if r.returncode != 0:
            raise UnexpectedProxyError("Failed to reload nginx")

    @classmethod
    def write_conf(cls, conf: str, conf_name: str) -> None:
        """Update config and reload nginx. Rollback changes on error."""
        conf_path = CONFIGS_DIR / conf_name
        old_conf = conf_path.read_text() if conf_path.exists() else None
        if conf == old_conf:
            return
        sudo_write(conf_path, conf)
        try:
            cls.reload()
        except UnexpectedProxyError:
            # rollback changes
            if old_conf is not None:
                sudo_write(conf_path, old_conf)
            else:
                sudo_rm(conf_path)
            raise

    def run_certbot(self, domain: str) -> None:
        logger.info("Running certbot for %s", domain)

        cmd = ["sudo", "certbot", "certonly"]
        cmd += ["--non-interactive", "--agree-tos", "--register-unsafely-without-email"]
        cmd += ["--keep", "--nginx", "--domain", domain]

        if self._acme_settings.server:
            cmd += ["--server", str(self._acme_settings.server)]

        if self._acme_settings.eab_kid and self._acme_settings.eab_hmac_key:
            cmd += ["--eab-kid", self._acme_settings.eab_kid]
            cmd += ["--eab-hmac-key", self._acme_settings.eab_hmac_key]

        r = subprocess.run(cmd, capture_output=True)
        if r.returncode != 0:
            raise ProxyError(f"Certbot failed:\n{r.stderr.decode()}")

    @staticmethod
    def get_config_name(domain: str) -> str:
        return f"443-{domain}.conf"

    @classmethod
    def write_global_conf(cls) -> None:
        conf = importlib.resources.read_text(RESOURCES_PACKAGE, "00-log-format.conf")
        cls.write_conf(conf, "00-log-format.conf")


def sudo_write(path: Path, content: str) -> None:
    with tempfile.NamedTemporaryFile("w") as temp:
        temp.write(content)
        temp.flush()
        temp.seek(0)
        r = subprocess.run(["sudo", "cp", "-p", temp.name, path])
        if r.returncode != 0:
            raise UnexpectedProxyError("Failed to copy file as sudo")


def sudo_rm(path: Path) -> None:
    r = subprocess.run(["sudo", "rm", path])
    if r.returncode != 0:
        raise UnexpectedProxyError("Failed to remove file as sudo")
