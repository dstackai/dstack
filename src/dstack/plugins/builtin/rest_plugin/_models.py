from typing import Generic, Optional, TypeVar

from pydantic import BaseModel, Field
from typing_extensions import Annotated

from dstack._internal.core.models.fleets import FleetSpec
from dstack._internal.core.models.gateways import GatewaySpec
from dstack._internal.core.models.runs import RunSpec
from dstack._internal.core.models.volumes import VolumeSpec

SpecType = TypeVar("SpecType", RunSpec, FleetSpec, VolumeSpec, GatewaySpec)


class SpecApplyRequest(BaseModel, Generic[SpecType]):
    user: Annotated[str, Field(description="The name of the user making the apply request")]
    project: Annotated[str, Field(description="The name of the project the request is for")]
    spec: Annotated[SpecType, Field(description="The spec to be applied")]

    # Override dict() to remove __orig_class__ attribute and avoid "TypeError: Object of type _GenericAlias is not JSON serializable"
    # error. This issue doesn't happen though when running the code in pytest, only when running the server.
    def dict(self, *args, **kwargs):
        d = super().dict(*args, **kwargs)
        d.pop("__orig_class__", None)
        return d


RunSpecRequest = SpecApplyRequest[RunSpec]
FleetSpecRequest = SpecApplyRequest[FleetSpec]
VolumeSpecRequest = SpecApplyRequest[VolumeSpec]
GatewaySpecRequest = SpecApplyRequest[GatewaySpec]


class SpecApplyResponse(BaseModel, Generic[SpecType]):
    spec: Annotated[
        SpecType,
        Field(
            description="The spec to apply, original spec if error otherwise original or mutated by plugin service if approved"
        ),
    ]
    error: Annotated[
        Optional[str], Field(description="Error message if request is rejected", min_length=1)
    ] = None


RunSpecResponse = SpecApplyResponse[RunSpec]
FleetSpecResponse = SpecApplyResponse[FleetSpec]
VolumeSpecResponse = SpecApplyResponse[VolumeSpec]
GatewaySpecResponse = SpecApplyResponse[GatewaySpec]
