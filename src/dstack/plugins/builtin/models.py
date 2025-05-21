from typing import Generic, TypeVar

from pydantic import BaseModel

from dstack._internal.core.models.fleets import FleetSpec
from dstack._internal.core.models.gateways import GatewaySpec
from dstack._internal.core.models.runs import RunSpec
from dstack._internal.core.models.volumes import VolumeSpec

SpecType = TypeVar("SpecType", RunSpec, FleetSpec, VolumeSpec, GatewaySpec)


class SpecApplyRequest(BaseModel, Generic[SpecType]):
    user: str
    project: str
    spec: SpecType

    def dict(self, *args, **kwargs):
        d = super().dict(*args, **kwargs)
        d.pop("__orig_class__", None)
        return d


RunSpecRequest = SpecApplyRequest[RunSpec]
FleetSpecRequest = SpecApplyRequest[FleetSpec]
VolumeSpecRequest = SpecApplyRequest[VolumeSpec]
GatewaySpecRequest = SpecApplyRequest[GatewaySpec]


class SpecApplyResponse(BaseModel, Generic[SpecType]):
    spec: SpecType
    error: str | None = None


RunSpecResponse = SpecApplyResponse[RunSpec]
FleetSpecResponse = SpecApplyResponse[FleetSpec]
VolumeSpecResponse = SpecApplyResponse[VolumeSpec]
GatewaySpecResponse = SpecApplyResponse[GatewaySpec]
