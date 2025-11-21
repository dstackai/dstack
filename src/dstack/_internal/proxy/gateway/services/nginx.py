import importlib.resources
import socket
import subprocess
import tempfile
from asyncio import Lock
from pathlib import Path
from typing import Dict, Optional

import jinja2
from pydantic import BaseModel
from typing_extensions import Literal

from dstack._internal.core.models.routers import AnyRouterConfig, RouterType
from dstack._internal.proxy.gateway.const import PROXY_PORT_ON_GATEWAY
from dstack._internal.proxy.gateway.models import ACMESettings
from dstack._internal.proxy.gateway.services.model_routers import (
    Router,
    RouterContext,
    get_router,
)
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
        render_dict = self.dict()
        render_dict["proxy_port"] = PROXY_PORT_ON_GATEWAY
        return jinja2.Template(template).render(**render_dict)


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
    router: Optional[AnyRouterConfig] = None
    router_port: Optional[int] = None


class ModelEntrypointConfig(SiteConfig):
    type: Literal["entrypoint"] = "entrypoint"
    project_name: str


class Nginx:
    """Updates nginx config and issues SSL certificates."""

    def __init__(self, conf_dir: Path = Path("/etc/nginx/sites-enabled")) -> None:
        self._conf_dir = conf_dir
        self._lock: Lock = Lock()
        # 1:1 service-to-router mapping
        self._router_port_to_domain: Dict[int, str] = {}
        self._domain_to_router: Dict[str, Router] = {}
        self._ROUTER_PORT_MIN: int = 20000
        self._ROUTER_PORT_MAX: int = 24999
        self._WORKER_PORT_MIN: int = 10001
        self._WORKER_PORT_MAX: int = 11999
        self._next_router_port: int = self._ROUTER_PORT_MIN
        # Tracking of worker ports to avoid conflicts across router instances
        self._allocated_worker_ports: set[int] = set()
        self._domain_to_worker_ports: Dict[str, list[int]] = {}
        self._next_worker_port: int = self._WORKER_PORT_MIN

    async def register(self, conf: SiteConfig, acme: ACMESettings) -> None:
        logger.debug("Registering %s domain %s", conf.type, conf.domain)
        conf_name = self.get_config_name(conf.domain)
        async with self._lock:
            if conf.https:
                await run_async(self.run_certbot, conf.domain, acme)

            if isinstance(conf, ServiceConfig) and conf.router:
                if conf.router.type == RouterType.SGLANG:
                    # Check if router already exists for this domain
                    if conf.domain in self._domain_to_router:
                        # Router already exists, reuse it
                        router = self._domain_to_router[conf.domain]
                        router_port = router.context.port
                        conf.router_port = router_port
                    else:
                        # Allocate router port for new router
                        router_port = self._allocate_router_port()
                        conf.router_port = router_port

                        # Create per-service log directory
                        log_dir = Path(f"./router_logs/{conf.domain}")

                        # Create router context with allocated port
                        ctx = RouterContext(
                            port=router_port,
                            log_dir=log_dir,
                        )

                        # Create new router instance for this service
                        router = get_router(conf.router, context=ctx)

                        # Store mappings
                        self._router_port_to_domain[router_port] = conf.domain
                        self._domain_to_router[conf.domain] = router

                        # Start router if not running
                        try:
                            if not await run_async(router.is_running):
                                await run_async(router.start)
                        except Exception:
                            # Clean up on failure
                            del self._router_port_to_domain[router_port]
                            del self._domain_to_router[conf.domain]
                            raise

                    allocated_ports = self._allocate_worker_ports(len(conf.replicas))
                    replica_urls = [
                        f"http://{router.context.host}:{port}" for port in allocated_ports
                    ]

                    # Write router workers config
                    try:
                        if conf.replicas:
                            await run_async(self.write_router_workers_conf, conf, allocated_ports)
                            # Discard old worker ports if domain already has allocated ports (required for scaling case)
                            if conf.domain in self._domain_to_worker_ports:
                                old_worker_ports = self._domain_to_worker_ports[conf.domain]
                                for port in old_worker_ports:
                                    self._allocated_worker_ports.discard(port)
                            self._domain_to_worker_ports[conf.domain] = allocated_ports
                    except Exception as e:
                        logger.exception(
                            "write_router_workers_conf failed for domain=%s: %s", conf.domain, e
                        )
                        raise

                    # Update replicas to router (actual HTTP API calls to add workers)
                    try:
                        await run_async(router.update_replicas, replica_urls)
                    except Exception as e:
                        logger.exception(
                            "Failed to add replicas to router for domain=%s: %s", conf.domain, e
                        )
                        raise

            await run_async(self.write_conf, conf.render(), conf_name)

        logger.info("Registered %s domain %s", conf.type, conf.domain)

    async def unregister(self, domain: str) -> None:
        logger.debug("Unregistering domain %s", domain)
        conf_path = self._conf_dir / self.get_config_name(domain)
        if not conf_path.exists():
            return
        async with self._lock:
            await run_async(sudo_rm, conf_path)

            if domain in self._domain_to_router:
                router = self._domain_to_router[domain]
                # Remove all workers for this domain
                if domain in self._domain_to_worker_ports:
                    worker_ports = self._domain_to_worker_ports[domain]
                    replica_urls = [
                        f"http://{router.context.host}:{port}" for port in worker_ports
                    ]
                    await run_async(router.remove_replicas, replica_urls)
                # Stop and kill the router
                await run_async(router.stop)
                # Remove from mappings
                router_port = router.context.port
                if router_port in self._router_port_to_domain:
                    del self._router_port_to_domain[router_port]
                del self._domain_to_router[domain]

                # Discard worker ports for this domain
                if domain in self._domain_to_worker_ports:
                    worker_ports = self._domain_to_worker_ports[domain]
                    for port in worker_ports:
                        self._allocated_worker_ports.discard(port)
                    del self._domain_to_worker_ports[domain]
                    logger.debug("Freed worker ports %s for domain %s", worker_ports, domain)

                # Remove workers config file
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

    @staticmethod
    def _is_port_available(port: int) -> bool:
        """Check if a port is actually available (not in use by any process).

        Tries to bind to the port to see if it's available.
        """
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                try:
                    sock.bind(("127.0.0.1", port))
                    # If bind succeeds, port is available
                    return True
                except OSError:
                    # If bind fails (e.g., Address already in use), port is not available
                    return False
        except Exception:
            logger.warning("Error checking port %s availability", port)
            return False

    def _allocate_router_port(self) -> int:
        """Allocate next available router port in fixed range.

        Checks both our internal allocation map and actual port availability
        to avoid conflicts with other services. Range chosen to avoid ephemeral ports.
        """
        port = self._next_router_port
        max_attempts = self._ROUTER_PORT_MAX - self._ROUTER_PORT_MIN + 1
        attempts = 0

        while attempts < max_attempts:
            # Check if port is already allocated by us
            if port in self._router_port_to_domain:
                port += 1
                if port > self._ROUTER_PORT_MAX:
                    port = self._ROUTER_PORT_MIN  # Wrap around
                attempts += 1
                continue

            # Check if port is actually available on the system
            if self._is_port_available(port):
                # Port is available, allocate it
                self._next_router_port = port + 1
                if self._next_router_port > self._ROUTER_PORT_MAX:
                    self._next_router_port = self._ROUTER_PORT_MIN  # Wrap around
                logger.debug("Allocated router port %s", port)
                return port

            # Port is in use, try next one
            logger.debug("Port %s is in use, trying next port", port)
            port += 1
            if port > self._ROUTER_PORT_MAX:
                port = self._ROUTER_PORT_MIN  # Wrap around
            attempts += 1

        raise UnexpectedProxyError(
            f"Router port range exhausted ({self._ROUTER_PORT_MIN}-{self._ROUTER_PORT_MAX}). "
            "All ports in range appear to be in use."
        )

    def _allocate_worker_ports(self, num_ports: int) -> list[int]:
        """Allocate worker ports globally in fixed range.

        Worker ports are used by nginx to listen and proxy to worker sockets.
        They must be unique across all router instances. Range chosen to avoid ephemeral ports.

        Args:
            num_ports: Number of worker ports to allocate

        Returns:
            List of allocated worker port numbers
        """
        allocated = []
        port = self._next_worker_port
        max_attempts = (self._WORKER_PORT_MAX - self._WORKER_PORT_MIN + 1) * 2  # Allow wrap-around
        attempts = 0

        while len(allocated) < num_ports and attempts < max_attempts:
            # Check if port is already allocated globally
            if port in self._allocated_worker_ports:
                port += 1
                if port > self._WORKER_PORT_MAX:
                    port = self._WORKER_PORT_MIN  # Wrap around
                attempts += 1
                continue

            # Check if port is actually available on the system
            if self._is_port_available(port):
                allocated.append(port)
                self._allocated_worker_ports.add(port)
                logger.debug("Allocated worker port %s", port)
                port += 1
                if port > self._WORKER_PORT_MAX:
                    port = self._WORKER_PORT_MIN  # Wrap around
            else:
                logger.debug("Worker port %s is in use, trying next port", port)
                port += 1
                if port > self._WORKER_PORT_MAX:
                    port = self._WORKER_PORT_MIN  # Wrap around

            attempts += 1

        if len(allocated) < num_ports:
            # Free up the ports we did allocate
            for p in allocated:
                self._allocated_worker_ports.discard(p)
            raise UnexpectedProxyError(
                f"Failed to allocate {num_ports} worker ports in range "
                f"({self._WORKER_PORT_MIN}-{self._WORKER_PORT_MAX}). "
                f"Only allocated {len(allocated)} ports after {attempts} attempts."
            )

        # Update next worker port for next allocation
        self._next_worker_port = port
        if self._next_worker_port > self._WORKER_PORT_MAX:
            self._next_worker_port = self._WORKER_PORT_MIN  # Wrap around

        return allocated

    def write_global_conf(self) -> None:
        conf = read_package_resource("00-log-format.conf")
        self.write_conf(conf, "00-log-format.conf")

    def write_router_workers_conf(self, conf: ServiceConfig, allocated_ports: list[int]) -> None:
        """Write router workers configuration file (generic)."""
        # Pass ports to template
        workers_config = generate_router_workers_config(conf, allocated_ports)
        workers_conf_name = f"router-workers.{conf.domain}.conf"
        self.write_conf(workers_config, workers_conf_name)


def generate_router_workers_config(conf: ServiceConfig, allocated_ports: list[int]) -> str:
    """Generate router workers configuration (generic, uses router_workers.jinja2 template)."""
    template = read_package_resource("router_workers.jinja2")
    return jinja2.Template(template).render(
        domain=conf.domain,
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
