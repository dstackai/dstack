from enum import Enum
from typing import Union

from pydantic import Field
from typing_extensions import Annotated, Literal

from dstack._internal.core.models.common import CoreModel


class RouterType(str, Enum):
    SGLANG = "sglang"
    VLLM = "vllm"


class SGLangRouterConfig(CoreModel):
    type: Literal["sglang"] = "sglang"
    policy: str = "cache_aware"


class VLLMRouterConfig(CoreModel):
    type: Literal["vllm"] = "vllm"
    policy: str = "cache_aware"


AnyRouterConfig = Annotated[
    Union[SGLangRouterConfig, VLLMRouterConfig], Field(discriminator="type")
]
