from enum import Enum
from typing import Literal

from pydantic import Field
from typing_extensions import Annotated

from dstack._internal.core.models.common import CoreModel


class RouterType(str, Enum):
    SGLANG = "sglang"
    DYNAMO = "dynamo"


class SGLangServiceRouterConfig(CoreModel):  # TODO: drop, unused by the server since 0.21.0
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
