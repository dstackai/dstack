from enum import Enum
from typing import Literal

from pydantic import Field
from typing_extensions import Annotated

from dstack._internal.core.models.common import CoreModel


class RouterType(str, Enum):
    SGLANG = "sglang"


class SGLangGatewayRouterConfig(CoreModel):
    """Gateway-level router configuration. type and policy only. pd_disaggregation is service-level."""

    type: Annotated[
        Literal["sglang"],
        Field(description="The router type enabled on this gateway."),
    ] = "sglang"
    policy: Annotated[
        Literal["random", "round_robin", "cache_aware", "power_of_two"],
        Field(
            description=(
                "The routing policy. Deprecated: prefer setting policy in the service's router config. "
                "Options: `random`, `round_robin`, `cache_aware`, `power_of_two`"
            ),
        ),
    ] = "cache_aware"


class SGLangServiceRouterConfig(CoreModel):
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


AnyServiceRouterConfig = SGLangServiceRouterConfig
AnyGatewayRouterConfig = SGLangGatewayRouterConfig
