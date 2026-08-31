from enum import Enum
from typing import Literal

from pydantic import Field
from typing_extensions import Annotated

from dstack._internal.core.models.common import CoreModel


class RouterType(str, Enum):
    SGLANG = "sglang"
    DYNAMO = "dynamo"


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
