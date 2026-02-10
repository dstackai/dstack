from enum import Enum
from typing import Literal, Optional

from pydantic import Field
from typing_extensions import Annotated

from dstack._internal.core.models.common import CoreModel


class RouterType(str, Enum):
    SGLANG = "sglang"


class SGLangRouterConfig(CoreModel):
    type: Annotated[Literal["sglang"], Field(description="The router type")] = "sglang"
    policy: Annotated[
        Literal["random", "round_robin", "cache_aware", "power_of_two"],
        Field(
            description="The routing policy. Options: `random`, `round_robin`, `cache_aware`, `power_of_two`"
        ),
    ] = "cache_aware"
    pd_disaggregation: Annotated[
        bool,
        Field(description="Enable PD disaggregation mode for the SGLang router"),
    ] = False


AnyRouterConfig = SGLangRouterConfig


def merge_router_config_for_service(
    gateway_router: Optional[AnyRouterConfig],
    service_router_config: Optional[AnyRouterConfig],
) -> Optional[AnyRouterConfig]:
    """Merge gateway and service router config.

    Gateway router config supplies the router type; service router config supplies
    policy and pd_disaggregation. The result combines both.
    """
    if gateway_router is None:
        return None
    if service_router_config is None:
        return gateway_router
    return SGLangRouterConfig(
        type=gateway_router.type,
        policy=service_router_config.policy,
        pd_disaggregation=service_router_config.pd_disaggregation,
    )
