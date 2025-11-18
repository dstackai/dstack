from enum import Enum
from typing import Literal

from dstack._internal.core.models.common import CoreModel


class RouterType(str, Enum):
    SGLANG = "sglang"


class SGLangRouterConfig(CoreModel):
    type: Literal["sglang"] = "sglang"
    policy: Literal["random", "round_robin", "cache_aware", "power_of_two"] = "cache_aware"


AnyRouterConfig = SGLangRouterConfig
