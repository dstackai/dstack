from typing import Generic, TypeVar

from pydantic import BaseModel

from dstack._internal.core.models.fleets import FleetSpec
from dstack._internal.core.models.gateways import GatewaySpec
from dstack._internal.core.models.runs import RunSpec
from dstack._internal.core.models.volumes import VolumeSpec

SpecType = TypeVar("SpecType", RunSpec, FleetSpec, VolumeSpec, GatewaySpec)


class SpecRequest(BaseModel, Generic[SpecType]):
    user: str
    project: str
    spec: SpecType


RunSpecRequest = SpecRequest[RunSpec]
FleetSpecRequest = SpecRequest[FleetSpec]
VolumeSpecRequest = SpecRequest[VolumeSpec]
GatewaySpecRequest = SpecRequest[GatewaySpec]
