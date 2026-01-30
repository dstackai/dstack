from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Literal, Optional

from pydantic import BaseModel

from dstack._internal.core.models.routers import AnyRouterConfig


class RouterContext(BaseModel):
    """Context for router initialization and configuration."""

    class Config:
        frozen = True

    host: str = "127.0.0.1"
    port: int
    log_dir: Path
    log_level: Literal["debug", "info", "warning", "error"] = "info"


class Router(ABC):
    """Abstract base class for router implementations.
    A router manages the lifecycle of worker replicas and handles request routing.
    Different router implementations may have different mechanisms for managing
    replicas.
    """

    def __init__(
        self,
        context: RouterContext,
        config: Optional[AnyRouterConfig] = None,
    ):
        """Initialize router with context.

        Args:
            context: Runtime context for the router (host, port, logging, etc.)
            config: Optional router configuration (implementation-specific)
        """
        self.context = context

    @abstractmethod
    def start(self) -> None:
        """Start the router process.

        Raises:
            Exception: If the router fails to start.
        """
        ...

    @abstractmethod
    def stop(self) -> None:
        """Stop the router process.

        Raises:
            Exception: If the router fails to stop.
        """
        ...

    @abstractmethod
    def is_running(self) -> bool:
        """Check if the router is currently running and responding.

        Returns:
            True if the router is running and healthy, False otherwise.
        """
        ...

    @abstractmethod
    def remove_replicas(self, replica_urls: List[str]) -> None:
        """Unregister replicas from the router (actual API calls to remove workers).

        Args:
            replica_urls: The list of replica URLs to remove from router.

        Raises:
            Exception: If removing replicas fails.
        """
        ...

    @abstractmethod
    async def update_replicas(self, replica_urls: List[str]) -> None:
        """Update replicas for service, replacing the current set.

        Args:
            replica_urls: The new list of replica URLs for this service.

        Raises:
            Exception: If updating replicas fails.
        """
        ...

    def add_worker_to_router(
        self,
        url: str,
        worker_type: str = "regular",
        bootstrap_port: Optional[int] = None,
    ) -> bool:
        """Add a worker to the router.

        Args:
            url: Worker URL (e.g. http://10.0.5.134:8000).
            worker_type: Type of worker ("regular", "prefill", or "decode").
            bootstrap_port: Bootstrap port for prefill workers (optional).

        Returns:
            True if the worker was accepted, False otherwise.
        """
        raise NotImplementedError

    async def register_worker(self, url: str) -> bool:
        """Register worker with one attempt (no polling). Returns True if ready and added."""
        raise NotImplementedError
