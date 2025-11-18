from typing import Optional

from dstack._internal.core.models.routers import AnyRouterConfig
from dstack._internal.proxy.gateway.model_routers.sglang import SglangRouter
from dstack._internal.proxy.lib.errors import ProxyError

from .base import Router, RouterContext


def get_router(router: AnyRouterConfig, context: Optional[RouterContext] = None) -> Router:
    if router.type == "sglang":
        return SglangRouter(config=router, context=context)
    raise ProxyError(f"Router type '{router.type}' is not available")


__all__ = [
    "Router",
    "RouterContext",
    "get_router",
]
