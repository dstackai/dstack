from typing import List

from typing_extensions import Literal

from dstack._internal.core.models.common import CoreModel


class DstackConfigInfo(CoreModel):
    type: Literal["dstack"] = "dstack"
    base_backends: List[str]


class DstackBaseBackendConfigInfo(CoreModel):
    type: str


class DstackConfigValues(CoreModel):
    type: Literal["dstack"] = "dstack"
