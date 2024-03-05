import importlib.resources
import logging
import re
import subprocess
import tempfile
from asyncio import Lock
from pathlib import Path
from typing import Set

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

    async def register_service(
        self, project: str, service_id: str, domain: str, auth: bool, fallback: str
    ):
        async with self._lock:
            if domain in self.domains:
                raise GatewayError(f"Domain {domain} is already registered")

            logger.debug("Registering service domain %s", domain)

            await run_async(self.run_certbot, domain)
            self.write_conf(
                self.get_service_conf(project, domain, auth, service_id, fallback),
                CONFIGS_DIR / f"443-{domain}.conf",
            )
            self.domains.add(domain)
            await run_async(self.reload)

        logger.info("Service domain %s is registered now", domain)

    async def register_entrypoint(self, domain: str, prefix: str):
        async with self._lock:
            if domain in self.domains:
                raise GatewayError(f"Domain {domain} is already registered")

            logger.debug("Registering entrypoint domain %s", domain)

            await run_async(self.run_certbot, domain)
            self.write_conf(
                self.get_entrypoint_conf(domain, prefix),
                CONFIGS_DIR / f"443-{domain}.conf",
            )
            self.domains.add(domain)
            await run_async(self.reload)

        logger.info("Entrypoint domain %s is registered now", domain)

    async def unregister_domain(self, domain: str):
        async with self._lock:
            if domain not in self.domains:
                raise GatewayError("Domain is not registered")

            logger.debug("Unregistering domain %s", domain)

            conf_path = CONFIGS_DIR / f"443-{domain}.conf"
            r = subprocess.run(["sudo", "rm", conf_path])
            if r.returncode != 0:
                raise GatewayError("Failed to remove nginx config")
            self.domains.remove(domain)
            await run_async(self.reload)

        logger.info("Domain %s is unregistered now", domain)

    async def add_upstream(self, domain: str, server: str, replica_id: str):
        async with self._lock:
            if domain not in self.domains:
                raise GatewayError("Domain is not registered")

            logger.debug("Adding upstream %s to domain %s", server, domain)

            config_path = CONFIGS_DIR / f"443-{domain}.conf"
            with open(config_path, "r") as f:
                conf = f.read()

            conf = self.add_upstream_to_conf(conf, server, replica_id)

            self.write_conf(conf, config_path)
            await run_async(self.reload)

        logger.debug("Upstream %s is added to domain %s", server, domain)

    async def remove_upstream(self, domain: str, replica_id: str):
        async with self._lock:
            if domain not in self.domains:
                raise GatewayError("Domain is not registered")

            logger.debug("Removing upstream %s from domain %s", replica_id, domain)

            config_path = CONFIGS_DIR / f"443-{domain}.conf"
            with open(config_path, "r") as f:
                conf = f.read()

            conf = self.remove_upstream_from_conf(conf, replica_id)

            self.write_conf(conf, config_path)
            await run_async(self.reload)

        logger.debug("Upstream %s is removed from domain %s", replica_id, domain)

    @classmethod
    def get_service_conf(
        cls, project: str, domain: str, auth: bool, upstream: str, fallback: str
    ) -> str:
        template = importlib.resources.read_text(
            "dstack.gateway.resources.nginx", "service.jinja2"
        )
        return jinja2.Template(template).render(
            upstream=upstream,
            fallback=fallback,
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

    @classmethod
    def add_upstream_to_conf(cls, conf: str, server: str, replica_id: str) -> str:
        return re.sub(
            r"(upstream +[^ ]+ *\{)",
            f"\\1\n  server {server}; # REPLICA:{replica_id}",
            conf,
        )

    @classmethod
    def remove_upstream_from_conf(cls, conf: str, replica_id: str) -> str:
        return re.sub(
            f" *server [^;]+; # REPLICA:{replica_id}\n",
            "",
            conf,
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
