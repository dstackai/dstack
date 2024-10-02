from typing import List

from dstack._internal.core.models.common import CoreModel
from dstack._internal.core.models.fleets import FleetSpec


class GetFleetRequest(CoreModel):
    name: str


class GetFleetPlanRequest(CoreModel):
    spec: FleetSpec


class CreateFleetRequest(CoreModel):
    spec: FleetSpec


class DeleteFleetsRequest(CoreModel):
    names: List[str]


class DeleteFleetInstancesRequest(CoreModel):
    name: str
    instance_nums: List[int]
