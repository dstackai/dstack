from typing import Dict, List, Optional, Type

from dstack._internal.core.models.routers import AnyRouterConfig, RouterType
from dstack._internal.utils.logging import get_logger

from .base import Replica, Router, RouterContext

logger = get_logger(__name__)

"""This provides a registry of available router implementations."""

_ROUTER_CLASSES: List[Type[Router]] = []

try:
    from dstack._internal.proxy.gateway.model_routers.sglang import SglangRouter

    _ROUTER_CLASSES.append(SglangRouter)
    logger.debug("Registered SglangRouter")
except ImportError as e:
    logger.warning("SGLang router not available: %s", e)

_ROUTER_TYPE_TO_CLASS_MAP: Dict[RouterType, Type[Router]] = {}

for router_class in _ROUTER_CLASSES:
    router_type_str = getattr(router_class, "TYPE", None)
    if router_type_str is None:
        logger.warning(f"Router class {router_class.__name__} missing TYPE attribute, skipping")
        continue
    router_type = RouterType(router_type_str)
    _ROUTER_TYPE_TO_CLASS_MAP[router_type] = router_class

_AVAILABLE_ROUTER_TYPES = list(_ROUTER_TYPE_TO_CLASS_MAP.keys())


def get_router_class(router_type: RouterType) -> Optional[Type[Router]]:
    """Get the router class for a given router type."""
    return _ROUTER_TYPE_TO_CLASS_MAP.get(router_type)


def get_router(router_config: AnyRouterConfig, context: Optional[RouterContext] = None) -> Router:
    """Factory function to create a router instance from router configuration."""
    router_type = RouterType(router_config.type)
    router_class = get_router_class(router_type)

    if router_class is None:
        available_types = [rt.value for rt in _AVAILABLE_ROUTER_TYPES]
        raise ValueError(
            f"Router type '{router_type.value}' is not available. "
            f"Available types: {available_types}"
        )

    # Router implementations may have different constructor signatures
    # SglangRouter takes (router_config, context), others might differ
    return router_class(router_config=router_config, context=context)


__all__ = [
    "Router",
    "RouterContext",
    "Replica",
    "get_router",
]
