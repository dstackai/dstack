import json
import shutil
import subprocess
import time
import urllib.parse
from typing import List, Optional

from dstack._internal.core.models.routers import RouterType, SGLangRouterConfig
from dstack._internal.proxy.gateway.const import DSTACK_DIR_ON_GATEWAY
from dstack._internal.proxy.lib.errors import UnexpectedProxyError
from dstack._internal.utils.logging import get_logger

from .base import Router, RouterContext

logger = get_logger(__name__)


class SglangRouter(Router):
    """SGLang router implementation with 1:1 service-to-router."""

    TYPE = RouterType.SGLANG

    def __init__(self, router: SGLangRouterConfig, context: Optional[RouterContext] = None):
        """Initialize SGLang router.

        Args:
            router: SGLang router configuration (policy, cache_threshold, etc.)
            context: Runtime context for the router (host, port, logging, etc.)
        """
        super().__init__(router=router, context=context)
        self.config = router

    def start(self) -> None:
        try:
            logger.info("Starting sglang-router-new on port %s...", self.context.port)

            # Determine active venv (blue or green)
            version_file = DSTACK_DIR_ON_GATEWAY / "version"
            if version_file.exists():
                version = version_file.read_text().strip()
            else:
                version = "blue"

            venv_python = DSTACK_DIR_ON_GATEWAY / version / "bin" / "python3"

            prometheus_port = self.context.port + 10000

            cmd = [
                str(venv_python),
                "-m",
                "sglang_router.launch_router",
                "--host",
                "0.0.0.0",
                "--port",
                str(self.context.port),
                "--prometheus-port",
                str(prometheus_port),
                "--log-level",
                self.context.log_level,
                "--log-dir",
                str(self.context.log_dir),
            ]

            if hasattr(self.config, "policy") and self.config.policy:
                cmd.extend(["--policy", self.config.policy])

            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            time.sleep(2)

            if not self.is_running():
                raise UnexpectedProxyError(
                    f"Failed to start sglang router on port {self.context.port}"
                )

            logger.info(
                "Sglang router started successfully on port %s (prometheus on %s)",
                self.context.port,
                prometheus_port,
            )

        except Exception as e:
            logger.error(f"Failed to start sglang-router-new: {e}")
            raise

    def stop(self) -> None:
        try:
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

    def remove_replicas(self, replica_urls: List[str]) -> None:
        for replica_url in replica_urls:
            self._remove_worker_from_router(replica_url)

    def update_replicas(self, replica_urls: List[str]) -> None:
        """Update replicas for service, replacing the current set."""
        # Query router to get current worker URLs
        current_workers = self._get_router_workers()
        current_worker_urls: set[str] = set()
        for worker in current_workers:
            url = worker.get("url")
            if url and isinstance(url, str):
                current_worker_urls.add(url)
        target_worker_urls = set(replica_urls)

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

        # Remove workers
        for worker_url in sorted(workers_to_remove):
            success = self._remove_worker_from_router(worker_url)
            if not success:
                logger.warning("Failed to remove worker %s, continuing with others", worker_url)

    def _get_router_workers(self) -> List[dict]:
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
        try:
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
        try:
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
