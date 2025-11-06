import json
import shutil
import subprocess
import time
import urllib.parse
from collections import defaultdict
from typing import DefaultDict, Dict, List, Optional

from dstack._internal.core.models.routers import SGLangRouterConfig
from dstack._internal.proxy.gateway.const import DSTACK_DIR_ON_GATEWAY
from dstack._internal.utils.logging import get_logger

from .base import Replica, Router, RouterContext

logger = get_logger(__name__)


class SglangRouter(Router):
    """SGLang router implementation using IGW (Inference Gateway) mode for multi-model serving."""

    TYPE = "sglang"

    def __init__(self, router_config: SGLangRouterConfig, context: Optional[RouterContext] = None):
        """Initialize SGLang router.

        Args:
            router_config: SGLang router configuration (policy, cache_threshold, etc.)
            context: Runtime context for the router (host, port, logging, etc.)
        """
        super().__init__(router_config=router_config, context=context)
        self.config = router_config
        self._domain_to_model_id: Dict[str, str] = {}  # domain -> model_id
        self._domain_to_ports: Dict[
            str, List[int]
        ] = {}  # domain -> allocated sglang worker ports.
        self._next_worker_port: int = 10001  # Starting port for worker endpoints

    def start(self) -> None:
        """Start the SGLang router process."""
        try:
            logger.info("Starting sglang-router...")

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
                "--enable-igw",
                "--log-level",
                self.context.log_level,
                "--log-dir",
                str(self.context.log_dir),
            ]

            if hasattr(self.config, "policy") and self.config.policy:
                cmd.extend(["--policy", self.config.policy])

            # Add additional required configs here

            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            # Wait for router to start
            time.sleep(2)

            # Verify router is running
            if not self.is_running():
                raise Exception("Failed to start sglang router")

            logger.info("Sglang router started successfully")

        except Exception as e:
            logger.error(f"Failed to start sglang-router: {e}")
            raise

    def stop(self) -> None:
        """Stop the SGLang router process."""
        try:
            result = subprocess.run(
                ["pgrep", "-f", "sglang::router"], capture_output=True, timeout=5
            )
            if result.returncode == 0:
                logger.info("Stopping sglang-router process...")
                subprocess.run(["pkill", "-f", "sglang::router"], timeout=5)
            else:
                logger.debug("No sglang-router process found to stop")

            # Clean up router logs
            if self.context.log_dir.exists():
                logger.debug("Cleaning up router logs...")
                shutil.rmtree(self.context.log_dir, ignore_errors=True)
            else:
                logger.debug("No router logs directory found to clean up")

        except Exception as e:
            logger.error(f"Failed to stop sglang-router: {e}")
            raise

    def is_running(self) -> bool:
        """Check if the SGLang router is running and responding to HTTP requests."""
        try:
            result = subprocess.run(
                ["curl", "-s", f"http://{self.context.host}:{self.context.port}/workers"],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except Exception as e:
            logger.error(f"Error checking sglang router status: {e}")
            return False

    def is_model_registered(self, model_id: str) -> bool:
        """Check if a model with the given model_id is registered."""
        return model_id in self._domain_to_model_id.values()

    def register_replicas(
        self, domain: str, num_replicas: int, model_id: Optional[str] = None
    ) -> List[Replica]:
        """Register replicas to a domain (allocate ports/URLs for workers).
        SGLang router uses IGW (Inference Gateway) mode, which requires model_id for multi-model serving.

        Maintains in-memory state:
        - domain_to_model_id: Maps domain to model_id for unregistering by domain and model validation.
        - domain_to_ports: Maps domain to allocated ports to track port assignments and avoid conflicts.

        Args:
            domain: The domain name for this service.
            num_replicas: The number of replicas to allocate for this domain.
            model_id: Model identifier (required for SGLang IGW mode).

        Raises:
            ValueError: If model_id is None (required for SGLang IGW mode).
        """
        if model_id is None:
            raise ValueError("model_id is required for SGLang router (IGW mode)")

        is_new_model = not self.is_model_registered(model_id)

        if is_new_model:
            # Store domain -> model_id mapping
            self._domain_to_model_id[domain] = model_id

            # Allocate ports for replicas
            allocated_ports = []
            for _ in range(num_replicas):
                allocated_ports.append(self._next_worker_port)
                self._next_worker_port += 1

            self._domain_to_ports[domain] = allocated_ports

            logger.debug(
                f"Allocated model {model_id} (domain {domain}) with {num_replicas} replicas "
                f"on ports {allocated_ports}"
            )
        else:
            # Verify domain matches
            if self._domain_to_model_id.get(domain) != model_id:
                raise ValueError(f"Domain {domain} does not match model_id {model_id}")

            # Get current allocated ports
            current_ports = self._domain_to_ports.get(domain, [])
            current_count = len(current_ports)

            if num_replicas == current_count:
                # No change needed, return existing replicas
                replicas = [
                    Replica(url=f"http://{self.context.host}:{port}", model=model_id)
                    for port in current_ports
                ]
                return replicas

            # Re-allocate ports for new count
            allocated_ports = []
            for _ in range(num_replicas):
                allocated_ports.append(self._next_worker_port)
                self._next_worker_port += 1

            self._domain_to_ports[domain] = allocated_ports

            logger.debug(
                f"Updated model {model_id} (domain {domain}) with {num_replicas} replicas "
                f"on ports {allocated_ports}"
            )

        # Create Replica objects with URLs and model_id
        replicas = [
            Replica(url=f"http://{self.context.host}:{port}", model=model_id)
            for port in allocated_ports
        ]
        return replicas

    def unregister_replicas(self, domain: str) -> None:
        """Unregister replicas for a domain (remove model and unassign all its replicas)."""
        # Get model_id from domain mapping
        model_id = self._domain_to_model_id.get(domain)
        if model_id is None:
            logger.warning(f"Domain {domain} not found in router mapping, skipping unregister")
            return

        # Remove all workers for this model_id from the router
        current_workers = self._get_router_workers(model_id)
        for worker in current_workers:
            self._remove_worker_from_router(worker["url"])

        # Clean up internal state
        if domain in self._domain_to_model_id:
            del self._domain_to_model_id[domain]
        if domain in self._domain_to_ports:
            del self._domain_to_ports[domain]

        logger.debug(f"Removed model {model_id} (domain {domain})")

    def add_replicas(self, replicas: List[Replica]) -> None:
        """Register replicas with the router (actual HTTP API calls to add workers)."""
        for replica in replicas:
            self._add_worker_to_router(replica.url, replica.model)

    def remove_replicas(self, replicas: List[Replica]) -> None:
        """Unregister replicas from the router (actual HTTP API calls to remove workers)."""
        for replica in replicas:
            self._remove_worker_from_router(replica.url)

    def update_replicas(self, replicas: List[Replica]) -> None:
        """Update replicas for a model, replacing the current set."""
        # Group replicas by model_id
        replicas_by_model: DefaultDict[str, List[Replica]] = defaultdict(list)
        for replica in replicas:
            replicas_by_model[replica.model].append(replica)

        # Update each model separately
        for model_id, model_replicas in replicas_by_model.items():
            # Get current workers for this model_id
            current_workers = self._get_router_workers(model_id)
            current_worker_urls = {worker["url"] for worker in current_workers}

            # Calculate target worker URLs
            target_worker_urls = {replica.url for replica in model_replicas}

            # Workers to add
            workers_to_add = target_worker_urls - current_worker_urls
            # Workers to remove
            workers_to_remove = current_worker_urls - target_worker_urls

            if workers_to_add:
                logger.info(
                    "Sglang router update: adding %d workers for model %s",
                    len(workers_to_add),
                    model_id,
                )
            if workers_to_remove:
                logger.info(
                    "Sglang router update: removing %d workers for model %s",
                    len(workers_to_remove),
                    model_id,
                )

            # Add workers
            for worker_url in sorted(workers_to_add):
                success = self._add_worker_to_router(worker_url, model_id)
                if not success:
                    logger.warning("Failed to add worker %s, continuing with others", worker_url)

            # Remove workers
            for worker_url in sorted(workers_to_remove):
                success = self._remove_worker_from_router(worker_url)
                if not success:
                    logger.warning(
                        "Failed to remove worker %s, continuing with others", worker_url
                    )

    def _get_router_workers(self, model_id: str) -> List[dict]:
        """Get all workers for a specific model_id from the router."""
        try:
            result = subprocess.run(
                ["curl", "-s", f"http://{self.context.host}:{self.context.port}/workers"],
                capture_output=True,
                timeout=5,
            )
            if result.returncode == 0:
                response = json.loads(result.stdout.decode())
                workers = response.get("workers", [])
                # Filter by model_id
                workers = [w for w in workers if w.get("model_id") == model_id]
                return workers
            return []
        except Exception as e:
            logger.error(f"Error getting sglang router workers: {e}")
            return []

    def _add_worker_to_router(self, worker_url: str, model_id: str) -> bool:
        """Add a single worker to the router."""
        try:
            payload = {"url": worker_url, "worker_type": "regular", "model_id": model_id}
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
                    logger.info("Added worker %s to sglang router", worker_url)
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
                    logger.info("Removed worker %s from sglang router", worker_url)
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
