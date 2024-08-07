from typing import List

from typing_extensions import Literal

from dstack._internal.core.models.common import CoreModel

# The OSS is currently aware of some of the DstackBackend internals (DstackConfigInfo) to be able to
# show DstackBackend base backends as regular backends.
# Consider designing an API that would allow DstackBackend to do the same without exposing its internals.


class DstackConfigInfo(CoreModel):
    """
    This is a config model of DstackBackend stored in BackendModel.config and used by DstackConfigurator.
    """

    type: Literal["dstack"] = "dstack"
    base_backends: List[str]


class DstackBaseBackendConfigInfo(CoreModel):
    type: str


class DstackConfigValues(CoreModel):
    type: Literal["dstack"] = "dstack"
