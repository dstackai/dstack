import importlib.resources
import logging
import re
import subprocess
import tempfile
from asyncio import Lock
from pathlib import Path
from typing import Optional, Set

import jinja2
from pydantic import BaseModel

from dstack.gateway.common import run_async
from dstack.gateway.errors import GatewayError

CONFIGS_DIR = Path("/etc/nginx/sites-enabled")
GATEWAY_PORT = 8000
logger = logging.getLogger(__name__)


class Nginx(BaseModel):
    """
    Nginx keeps track of registered domains, updates nginx config and issues SSL certificates.
    Its internal state could be serialized to a file and restored from it using pydantic.
    """

    domains: Set[str] = set()
    _lock: Lock = Lock()

    async def register_service(self, project: str, domain: str, sock_path: str, auth: bool):
        logger.info("Registering service %s", domain)
        async with self._lock:
            if domain in self.domains:
                raise GatewayError("Domain is already registered")
            self.write_conf(
                self.get_service_conf(project, domain, f"unix:{sock_path}", auth),
                CONFIGS_DIR / f"443-{domain}.conf",
            )
            self.domains.add(domain)
            await run_async(self.reload)

    async def register_entrypoint(self, domain: str, prefix: str):
        logger.info("Registering entrypoint %s", domain)
        async with self._lock:
            if domain in self.domains:
                raise GatewayError("Domain is already registered")
            await run_async(self.run_certbot, domain)
            self.write_conf(
                self.get_entrypoint_conf(domain, prefix),
                CONFIGS_DIR / f"443-{domain}.conf",
            )
            self.domains.add(domain)
            await run_async(self.reload)

    async def unregister_domain(self, domain: str):
        logger.info("Unregistering domain %s", domain)
        async with self._lock:
            if domain not in self.domains:
                raise GatewayError("Domain is not registered")
            conf_path = CONFIGS_DIR / f"443-{domain}.conf"
            r = subprocess.run(["sudo", "rm", conf_path])
            if r.returncode != 0:
                raise GatewayError("Failed to remove nginx config")
            self.domains.remove(domain)
            await run_async(self.reload)

    @classmethod
    def get_service_conf(
        cls, project: str, domain: str, server: str, auth: bool, upstream: Optional[str] = None
    ) -> str:
        if upstream is None:
            upstream = re.sub(r"[^a-z0-9_.\-]", "_", server, flags=re.IGNORECASE)
        template = importlib.resources.read_text(
            "dstack.gateway.resources.nginx", "service.jinja2"
        )
        return jinja2.Template(template).render(
            upstream=upstream,
            server=server,
            domain=domain,
            auth=auth,
            port=GATEWAY_PORT,
            project=project,
        )

    @classmethod
    def get_entrypoint_conf(cls, domain: str, prefix: str) -> str:
        template = importlib.resources.read_text(
            "dstack.gateway.resources.nginx", "entrypoint.jinja2"
        )
        return jinja2.Template(template).render(
            domain=domain,
            port=GATEWAY_PORT,
            prefix=prefix,
        )

    @staticmethod
    def reload():
        cmd = ["sudo", "systemctl", "reload", "nginx.service"]
        r = subprocess.run(cmd)
        if r.returncode != 0:
            raise GatewayError("Failed to reload nginx")

    @classmethod
    def write_conf(cls, conf: str, conf_path: Path):
        temp = tempfile.NamedTemporaryFile("w")
        temp.write(conf)
        temp.flush()
        temp.seek(0)
        r = subprocess.run(["sudo", "cp", temp.name, conf_path])
        if r.returncode != 0:
            raise GatewayError("Failed to write nginx config")

    @staticmethod
    def run_certbot(domain: str):
        logger.info("Running certbot for %s", domain)
        cmd = ["sudo", "certbot", "certonly"]
        cmd += ["--non-interactive", "--agree-tos", "--register-unsafely-without-email"]
        cmd += ["--nginx", "--domain", domain]
        r = subprocess.run(cmd, capture_output=True)
        if r.returncode != 0:
            raise GatewayError(f"Certbot failed:\n{r.stderr.decode()}")
