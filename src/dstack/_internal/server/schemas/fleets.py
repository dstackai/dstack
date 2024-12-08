from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import Field

from dstack._internal.core.models.common import CoreModel
from dstack._internal.core.models.fleets import FleetSpec


class ListFleetsRequest(CoreModel):
    project_name: Optional[str]
    only_active: bool = False
    prev_created_at: Optional[datetime]
    prev_id: Optional[UUID]
    limit: int = Field(100, ge=0, le=100)
    ascending: bool = False


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
