import logging
import re
import subprocess
import tempfile
from asyncio import Lock
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from dstack.gateway.common import run_async
from dstack.gateway.errors import GatewayError

CONFIGS_DIR = Path("/etc/nginx/sites-enabled")
logger = logging.getLogger(__name__)


class Nginx:
    def __init__(self):
        self.lock = Lock()
        self.domains = set()

    async def register_service(self, domain: str, sock_path: str):
        logger.info("Registering service %s", domain)
        async with self.lock:
            if domain in self.domains:
                raise GatewayError("Domain is already registered")
            await run_async(run_certbot, domain)
            self.write_conf(
                self.get_conf(domain, f"unix:{sock_path}"),
                CONFIGS_DIR / f"443-{domain}.conf",
            )
            self.domains.add(domain)
            await run_async(self.reload)

    async def unregister_service(self, domain: str):
        logger.info("Unregistering service %s", domain)
        async with self.lock:
            if domain not in self.domains:
                raise GatewayError("Domain is not registered")
            conf_path = CONFIGS_DIR / f"443-{domain}.conf"
            r = subprocess.run(["sudo", "rm", conf_path])
            if r.returncode != 0:
                raise GatewayError("Failed to remove nginx config")
            self.domains.remove(domain)
            await run_async(self.reload)

    @staticmethod
    def get_conf(domain: str, server: str, upstream: Optional[str] = None) -> dict:
        if upstream is None:
            upstream = re.sub(r"[^a-z0-9_.\-]", "_", server, flags=re.IGNORECASE)
        return {
            f"upstream {upstream}": {
                "server": server,
            },
            "server": {
                "server_name": domain,
                "location /": {
                    # the first location is required, always fallback to the @-location
                    "try_files": "/nonexistent @$http_upgrade",
                },
                "location @websocket": {
                    "proxy_pass": f"http://{upstream}",
                    "proxy_set_header X-Real-IP": "$remote_addr",
                    "proxy_set_header Host": "$host",
                    # web socket related headers
                    "proxy_http_version": "1.1",
                    "proxy_set_header Upgrade": "$http_upgrade",
                    "proxy_set_header Connection": '"Upgrade"',
                },
                "location @": {
                    "proxy_pass": f"http://{upstream}",
                    "proxy_set_header X-Real-IP": "$remote_addr",
                    "proxy_set_header Host": "$host",
                },
                "listen": "80",
                "listen 443": "ssl",
                "ssl_certificate": f"/etc/letsencrypt/live/{domain}/fullchain.pem",
                "ssl_certificate_key": f"/etc/letsencrypt/live/{domain}/privkey.pem",
                "include": "/etc/letsencrypt/options-ssl-nginx.conf",
                "ssl_dhparam": "/etc/letsencrypt/ssl-dhparams.pem",
                # do not force https for localhost
                # we rely on ordered dict (3.8+)
                "set $force_https": "1",
                'if ($scheme = "https")': {
                    "set $force_https": "0",
                },
                "if ($remote_addr = 127.0.0.1)": {
                    "set $force_https": "0",
                },
                "if ($force_https)": {
                    "return": "301 https://$host$request_uri",
                },
            },
        }

    @staticmethod
    def reload():
        cmd = ["sudo", "systemctl", "reload", "nginx.service"]
        r = subprocess.run(cmd)
        if r.returncode != 0:
            raise GatewayError("Failed to reload nginx")

    @classmethod
    def format_conf(
        cls, o: Union[Dict[str, Any], List[Tuple[str, Any]]], *, indent: int = 2, depth: int = 0
    ) -> str:
        pad = " " * depth * indent
        text = ""
        pairs = o.items() if isinstance(o, dict) else o
        for key, value in pairs:
            if isinstance(value, (dict, list)):
                text += pad + key + " {\n"
                text += cls.format_conf(value, indent=indent, depth=depth + 1)
                text += pad + "}\n"
            else:
                text += pad + f"{key} {value};\n"
        return text

    @classmethod
    def write_conf(cls, conf: dict, conf_path: Path):
        temp = tempfile.NamedTemporaryFile("w")
        temp.write(cls.format_conf(conf))
        temp.flush()
        temp.seek(0)
        r = subprocess.run(["sudo", "cp", temp.name, conf_path])
        if r.returncode != 0:
            raise GatewayError("Failed to write nginx config")


def run_certbot(domain: str):
    logger.info("Running certbot for %s", domain)
    cmd = ["sudo", "certbot", "certonly"]
    cmd += ["--non-interactive", "--agree-tos", "--register-unsafely-without-email"]
    cmd += ["--nginx", "--domain", domain]
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0:
        raise GatewayError(f"Certbot failed:\n{r.stderr.decode()}")


@lru_cache()
def get_nginx() -> Nginx:
    return Nginx()
