import json
import shutil
import subprocess
import time
import urllib.parse
from typing import Dict, List, Optional

from dstack._internal.core.models.routers import SGLangNewRouterConfig
from dstack._internal.proxy.gateway.const import DSTACK_DIR_ON_GATEWAY
from dstack._internal.utils.logging import get_logger

from .base import Replica, Router, RouterContext

logger = get_logger(__name__)


class SglangRouterNew(Router):
    """SGLang router implementation with 1:1 service-to-router mapping (no IGW mode)."""

    TYPE = "sglang"

    def __init__(self, router: SGLangNewRouterConfig, context: Optional[RouterContext] = None):
        """Initialize SGLang router.

        Args:
            router: SGLang router configuration (policy, cache_threshold, etc.)
            context: Runtime context for the router (host, port, logging, etc.)
        """
        super().__init__(router=router, context=context)
        self.config = router
        self._domain: Optional[str] = None  # domain for this router instance
        self._replica_urls: List[str] = []  # List of worker URLs registered with this router
        self._domain_to_ports: Dict[str, List[int]] = {}  # domain -> allocated worker ports
        self._next_worker_port: int = (
            12000  # Starting port for worker endpoints (avoid router port range 10001-11999)
        )

    def start(self) -> None:
        """Start the SGLang router process."""
        try:
            logger.info("Starting sglang-router-new on port %s...", self.context.port)

            # Determine active venv (blue or green)
            version_file = DSTACK_DIR_ON_GATEWAY / "version"
            if version_file.exists():
                version = version_file.read_text().strip()
            else:
                version = "blue"

            # Use Python from the active venv
            venv_python = DSTACK_DIR_ON_GATEWAY / version / "bin" / "python3"

            cmd = [
                str(venv_python),
                "-m",
                "sglang_router.launch_router",
                "--host",
                "0.0.0.0",  # Bind to all interfaces (nginx connects via 127.0.0.1)
                "--port",
                str(self.context.port),
                # Note: No --enable-igw flag for this router type
                "--log-level",
                self.context.log_level,
                "--log-dir",
                str(self.context.log_dir),
            ]

            if hasattr(self.config, "policy") and self.config.policy:
                cmd.extend(["--policy", self.config.policy])

            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            # Wait for router to start
            time.sleep(2)

            # Verify router is running
            if not self.is_running():
                raise Exception(f"Failed to start sglang router on port {self.context.port}")

            logger.info("Sglang router started successfully on port %s", self.context.port)

        except Exception as e:
            logger.error(f"Failed to start sglang-router-new: {e}")
            raise

    def stop(self) -> None:
        """Stop the SGLang router process by port."""
        try:
            # Find process listening on the router port
            result = subprocess.run(
                ["lsof", "-ti", f":{self.context.port}"], capture_output=True, timeout=5
            )
            if result.returncode == 0:
                pids = result.stdout.decode().strip().split("\n")
                for pid in pids:
                    if pid:
                        logger.info(
                            "Stopping sglang-router-new process (PID: %s) on port %s",
                            pid,
                            self.context.port,
                        )
                        subprocess.run(["kill", pid], timeout=5)
            else:
                # Fallback: try pgrep with port-based pattern
                result = subprocess.run(
                    ["pgrep", "-f", f"sglang.*--port.*{self.context.port}"],
                    capture_output=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    pids = result.stdout.decode().strip().split("\n")
                    for pid in pids:
                        if pid:
                            logger.info("Stopping sglang-router-new process (PID: %s)", pid)
                            subprocess.run(["kill", pid], timeout=5)
                else:
                    logger.debug(
                        "No sglang-router-new process found on port %s", self.context.port
                    )

            # Clean up router logs
            if self.context.log_dir.exists():
                logger.debug("Cleaning up router logs for port %s...", self.context.port)
                shutil.rmtree(self.context.log_dir, ignore_errors=True)
            else:
                logger.debug("No router logs directory found to clean up")

        except Exception as e:
            logger.error(f"Failed to stop sglang-router-new: {e}")
            raise

    def is_running(self) -> bool:
        """Check if the SGLang router is running and responding to HTTP requests on the assigned port."""
        try:
            result = subprocess.run(
                ["curl", "-s", f"http://{self.context.host}:{self.context.port}/workers"],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except Exception as e:
            logger.error(f"Error checking sglang router status on port {self.context.port}: {e}")
            return False

    def register_replicas(
        self, domain: str, num_replicas: int, model_id: Optional[str] = None
    ) -> List[Replica]:
        """Register replicas to a domain (allocate ports/URLs for workers).

        For sglang_new, model_id is not required since we don't use IGW mode.
        This method allocates worker ports and returns Replica objects with those ports.

        Args:
            domain: The domain name for this service.
            num_replicas: The number of replicas to allocate for this domain.
            model_id: Model identifier (optional, not used in non-IGW mode).

        Returns:
            List of Replica objects with allocated worker ports.
        """
        self._domain = domain

        # Allocate ports for replicas
        allocated_ports = []
        for _ in range(num_replicas):
            allocated_ports.append(self._next_worker_port)
            self._next_worker_port += 1

        self._domain_to_ports[domain] = allocated_ports

        logger.debug(
            f"Allocated domain {domain} with {num_replicas} replicas "
            f"on ports {allocated_ports} for router on port {self.context.port}"
        )

        # Create Replica objects with URLs (model_id is empty for sglang_new)
        replicas = [
            Replica(url=f"http://{self.context.host}:{port}", model=model_id or "")
            for port in allocated_ports
        ]
        return replicas

    def unregister_replicas(self, domain: str) -> None:
        """Unregister replicas for a domain (remove all workers from router)."""
        if self._domain != domain:
            logger.warning(
                f"Domain {domain} does not match router domain {self._domain}, skipping unregister"
            )
            return

        # Remove all workers from the router
        for replica_url in self._replica_urls[:]:  # Copy list to iterate safely
            self._remove_worker_from_router(replica_url)

        # Clear internal state
        self._replica_urls.clear()
        if domain in self._domain_to_ports:
            del self._domain_to_ports[domain]
        self._domain = None

        logger.debug(
            f"Removed all workers for domain {domain} from router on port {self.context.port}"
        )

    def add_replicas(self, replicas: List[Replica]) -> None:
        """Register replicas with the router (actual HTTP API calls to add workers)."""
        for replica in replicas:
            success = self._add_worker_to_router(replica.url)
            if success:
                if replica.url not in self._replica_urls:
                    self._replica_urls.append(replica.url)

    def remove_replicas(self, replicas: List[Replica]) -> None:
        """Unregister replicas from the router (actual HTTP API calls to remove workers)."""
        for replica in replicas:
            success = self._remove_worker_from_router(replica.url)
            if success:
                if replica.url in self._replica_urls:
                    self._replica_urls.remove(replica.url)

    def update_replicas(self, replicas: List[Replica]) -> None:
        """Update replicas for service, replacing the current set."""
        # Get current worker URLs
        current_worker_urls = set(self._replica_urls)
        target_worker_urls = {replica.url for replica in replicas}

        # Workers to add
        workers_to_add = target_worker_urls - current_worker_urls
        # Workers to remove
        workers_to_remove = current_worker_urls - target_worker_urls

        if workers_to_add:
            logger.info(
                "Sglang router update: adding %d workers for router on port %s",
                len(workers_to_add),
                self.context.port,
            )
        if workers_to_remove:
            logger.info(
                "Sglang router update: removing %d workers for router on port %s",
                len(workers_to_remove),
                self.context.port,
            )

        # Add workers
        for worker_url in sorted(workers_to_add):
            success = self._add_worker_to_router(worker_url)
            if not success:
                logger.warning("Failed to add worker %s, continuing with others", worker_url)
            else:
                if worker_url not in self._replica_urls:
                    self._replica_urls.append(worker_url)

        # Remove workers
        for worker_url in sorted(workers_to_remove):
            success = self._remove_worker_from_router(worker_url)
            if not success:
                logger.warning("Failed to remove worker %s, continuing with others", worker_url)
            else:
                if worker_url in self._replica_urls:
                    self._replica_urls.remove(worker_url)

    def _get_router_workers(self) -> List[dict]:
        """Get all workers from the router."""
        try:
            result = subprocess.run(
                ["curl", "-s", f"http://{self.context.host}:{self.context.port}/workers"],
                capture_output=True,
                timeout=5,
            )
            if result.returncode == 0:
                response = json.loads(result.stdout.decode())
                workers = response.get("workers", [])
                return workers
            return []
        except Exception as e:
            logger.error(f"Error getting sglang router workers: {e}")
            return []

    def _add_worker_to_router(self, worker_url: str) -> bool:
        """Add a single worker to the router."""
        try:
            # For non-IGW mode, model_id is not needed
            payload = {"url": worker_url, "worker_type": "regular"}
            result = subprocess.run(
                [
                    "curl",
                    "-X",
                    "POST",
                    f"http://{self.context.host}:{self.context.port}/workers",
                    "-H",
                    "Content-Type: application/json",
                    "-d",
                    json.dumps(payload),
                ],
                capture_output=True,
                timeout=5,
            )

            if result.returncode == 0:
                response = json.loads(result.stdout.decode())
                if response.get("status") == "accepted":
                    logger.info(
                        "Added worker %s to sglang router on port %s",
                        worker_url,
                        self.context.port,
                    )
                    return True
                else:
                    logger.error("Failed to add worker %s: %s", worker_url, response)
                    return False
            else:
                logger.error("Failed to add worker %s: %s", worker_url, result.stderr.decode())
                return False
        except Exception as e:
            logger.error(f"Error adding worker {worker_url}: {e}")
            return False

    def _remove_worker_from_router(self, worker_url: str) -> bool:
        """Remove a single worker from the router."""
        try:
            # URL encode the worker URL for the DELETE request
            encoded_url = urllib.parse.quote(worker_url, safe="")

            result = subprocess.run(
                [
                    "curl",
                    "-X",
                    "DELETE",
                    f"http://{self.context.host}:{self.context.port}/workers/{encoded_url}",
                ],
                capture_output=True,
                timeout=5,
            )

            if result.returncode == 0:
                response = json.loads(result.stdout.decode())
                if response.get("status") == "accepted":
                    logger.info(
                        "Removed worker %s from sglang router on port %s",
                        worker_url,
                        self.context.port,
                    )
                    return True
                else:
                    logger.error("Failed to remove worker %s: %s", worker_url, response)
                    return False
            else:
                logger.error("Failed to remove worker %s: %s", worker_url, result.stderr.decode())
                return False
        except Exception as e:
            logger.error(f"Error removing worker {worker_url}: {e}")
            return False
