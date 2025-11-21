import shutil
import subprocess
import sys
import time
import urllib.parse
from typing import List, Optional

import httpx
import psutil

from dstack._internal.core.models.routers import RouterType, SGLangRouterConfig
from dstack._internal.proxy.lib.errors import UnexpectedProxyError
from dstack._internal.utils.logging import get_logger

from .base import Router, RouterContext

logger = get_logger(__name__)


class SglangRouter(Router):
    """SGLang router implementation with 1:1 service-to-router."""

    TYPE = RouterType.SGLANG

    def __init__(self, config: SGLangRouterConfig, context: RouterContext):
        """Initialize SGLang router.

        Args:
            config: SGLang router configuration (policy, cache_threshold, etc.)
            context: Runtime context for the router (host, port, logging, etc.)
        """
        super().__init__(context=context, config=config)
        self.config = config

    def pid_from_tcp_ipv4_port(self, port: int) -> Optional[int]:
        """
        Return PID of the process listening on the given TCP IPv4 port.
        If no process is found, return None.
        """
        for conn in psutil.net_connections(kind="tcp4"):
            if conn.laddr and conn.laddr.port == port and conn.status == psutil.CONN_LISTEN:
                return conn.pid
        return None

    def start(self) -> None:
        try:
            logger.info("Starting sglang-router-new on port %s...", self.context.port)

            # Prometheus port is offset by 10000 from router port to keep it in a separate range
            prometheus_port = self.context.port + 10000

            cmd = [
                sys.executable,
                "-m",
                "sglang_router.launch_router",
                "--host",
                self.context.host,
                "--port",
                str(self.context.port),
                "--prometheus-port",
                str(prometheus_port),
                "--prometheus-host",
                self.context.host,
                "--log-level",
                self.context.log_level,
                "--log-dir",
                str(self.context.log_dir),
                "--policy",
                self.config.policy,
            ]

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

        except Exception:
            logger.exception("Failed to start sglang-router")
            raise

    def stop(self) -> None:
        try:
            pid = self.pid_from_tcp_ipv4_port(self.context.port)

            if pid:
                logger.debug(
                    "Stopping sglang-router process (PID: %s) on port %s",
                    pid,
                    self.context.port,
                )
                try:
                    proc = psutil.Process(pid)
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except psutil.TimeoutExpired:
                        logger.warning(
                            "Process %s did not terminate gracefully, forcing kill", pid
                        )
                        proc.kill()
                except psutil.NoSuchProcess:
                    logger.debug("sglang-router process %s already exited before stop()", pid)
            else:
                logger.debug("No sglang-router process found on port %s", self.context.port)

            # Clean up router logs
            if self.context.log_dir.exists():
                logger.debug("Cleaning up router logs for port %s...", self.context.port)
                shutil.rmtree(self.context.log_dir, ignore_errors=True)

        except Exception:
            logger.exception("Failed to stop sglang-router")
            raise

    def is_running(self) -> bool:
        """Check if the SGLang router is running and responding to HTTP requests on the assigned port."""
        try:
            with httpx.Client(timeout=5.0) as client:
                response = client.get(f"http://{self.context.host}:{self.context.port}/workers")
                return response.status_code == 200
        except httpx.RequestError as e:
            logger.debug(
                "Sglang router not responding on port %s: %s",
                self.context.port,
                e,
            )
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
                # Normalize URL by removing trailing slashes to avoid path artifacts
                normalized_url = url.rstrip("/")
                current_worker_urls.add(normalized_url)
        # Normalize target URLs to ensure consistent comparison
        target_worker_urls = {url.rstrip("/") for url in replica_urls}

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
            with httpx.Client(timeout=5.0) as client:
                response = client.get(f"http://{self.context.host}:{self.context.port}/workers")
                if response.status_code == 200:
                    response_data = response.json()
                    workers = response_data.get("workers", [])
                    return workers
                return []
        except Exception:
            logger.exception("Error getting sglang router workers")
            return []

    def _add_worker_to_router(self, worker_url: str) -> bool:
        try:
            payload = {"url": worker_url, "worker_type": "regular"}
            with httpx.Client(timeout=5.0) as client:
                response = client.post(
                    f"http://{self.context.host}:{self.context.port}/workers",
                    json=payload,
                )
                if response.status_code == 202:
                    response_data = response.json()
                    if response_data.get("status") == "accepted":
                        logger.info(
                            "Worker %s accepted by sglang router on port %s",
                            worker_url,
                            self.context.port,
                        )
                        return True
                    else:
                        logger.error(
                            "Sglang router on port %s failed to accept worker: %s",
                            self.context.port,
                            response_data,
                        )
                        return False
                else:
                    logger.error(
                        "Failed to add worker %s: status %d, %s",
                        worker_url,
                        response.status_code,
                        response.text,
                    )
                    return False
        except Exception:
            logger.exception("Error adding worker %s", worker_url)
            return False

    def _remove_worker_from_router(self, worker_url: str) -> bool:
        try:
            encoded_url = urllib.parse.quote(worker_url, safe="")
            with httpx.Client(timeout=5.0) as client:
                response = client.delete(
                    f"http://{self.context.host}:{self.context.port}/workers/{encoded_url}"
                )
                if response.status_code == 202:
                    response_data = response.json()
                    if response_data.get("status") == "accepted":
                        logger.info(
                            "Removed worker %s from sglang router on port %s",
                            worker_url,
                            self.context.port,
                        )
                        return True
                    else:
                        logger.error(
                            "Sglang router on port %s failed to remove worker: %s",
                            self.context.port,
                            response_data,
                        )
                        return False
                else:
                    logger.error(
                        "Failed to remove worker %s: status %d, %s",
                        worker_url,
                        response.status_code,
                        response.text,
                    )
                    return False
        except Exception:
            logger.exception("Error removing worker %s", worker_url)
            return False
