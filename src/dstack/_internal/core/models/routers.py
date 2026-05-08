from enum import Enum
from typing import Literal

from pydantic import Field
from typing_extensions import Annotated

from dstack._internal.core.models.common import CoreModel


class RouterType(str, Enum):
    SGLANG = "sglang"
    DYNAMO = "dynamo"


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


class ReplicaGroupRouterConfig(CoreModel):
    type: Annotated[
        Literal["sglang", "dynamo"],
        Field(
            description=(
                "The router implementation for this replica group. "
                "`sglang` runs the SGLang router and dstack syncs worker URLs to it. "
                "`dynamo` runs the NVIDIA Dynamo frontend, which discovers workers "
                "itself via etcd/NATS."
            ),
        ),
    ] = "sglang"


AnyServiceRouterConfig = SGLangServiceRouterConfig
AnyGatewayRouterConfig = SGLangGatewayRouterConfig
