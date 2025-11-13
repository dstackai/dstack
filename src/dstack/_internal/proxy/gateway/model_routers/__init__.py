from typing import Optional

from dstack._internal.core.models.routers import AnyRouterConfig
from dstack._internal.proxy.gateway.model_routers.sglang import SglangRouter

from .base import Router, RouterContext


def get_router(router: AnyRouterConfig, context: Optional[RouterContext] = None) -> Router:
    """Factory function to create a router instance from router configuration."""
    if router.type == "sglang":
        return SglangRouter(router=router, context=context)
    raise ValueError(f"Router type '{router.type}' is not available")


__all__ = [
    "Router",
    "RouterContext",
    "get_router",
]
