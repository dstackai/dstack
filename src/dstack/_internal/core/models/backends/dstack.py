from typing_extensions import Literal

from dstack._internal.core.models.common import CoreModel


class DstackConfigInfo(CoreModel):
    type: Literal["dstack"] = "dstack"


class DstackConfigValues(CoreModel):
    type: Literal["dstack"] = "dstack"
