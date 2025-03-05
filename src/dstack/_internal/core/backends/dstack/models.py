from typing import Annotated, List, Literal

from pydantic import Field

from dstack._internal.core.models.common import CoreModel

# The OSS is currently aware of some of the DstackBackend internals (DstackBackendConfig) to be able to
# show DstackBackend base backends as regular backends.
# Consider designing an API that would allow DstackBackend to do the same without exposing its internals.


class DstackBackendConfig(CoreModel):
    """
    This is a config model of DstackBackend stored in BackendModel.config and used by DstackConfigurator.
    """

    type: Literal["dstack"] = "dstack"
    base_backends: List[str]


class DstackBaseBackendConfig(CoreModel):
    type: str


class DstackConfig(CoreModel):
    type: Annotated[Literal["dstack"], Field(description="The type of backend")] = "dstack"
