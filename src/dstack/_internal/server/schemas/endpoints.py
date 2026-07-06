from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import Field

from dstack._internal.core.models.common import CoreModel
from dstack._internal.core.models.endpoints import EndpointConfiguration


class ListEndpointsRequest(CoreModel):
    project_name: Optional[str]
    only_active: bool = False
    prev_created_at: Optional[datetime]
    prev_id: Optional[UUID]
    limit: int = Field(100, ge=0, le=100)
    ascending: bool = False


class GetEndpointRequest(CoreModel):
    name: str


class GetEndpointPlanRequest(CoreModel):
    configuration: EndpointConfiguration
    configuration_path: Optional[str] = None


class CreateEndpointRequest(CoreModel):
    configuration: EndpointConfiguration


class StopEndpointsRequest(CoreModel):
    names: List[str]
