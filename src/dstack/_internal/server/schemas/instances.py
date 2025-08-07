from datetime import datetime
from typing import Optional
from uuid import UUID

from dstack._internal.core.models.common import CoreModel
from dstack._internal.core.models.health import HealthCheck, HealthStatus
from dstack._internal.server.schemas.runner import InstanceHealthResponse


class ListInstancesRequest(CoreModel):
    project_names: Optional[list[str]] = None
    fleet_ids: Optional[list[UUID]] = None
    only_active: bool = False
    prev_created_at: Optional[datetime] = None
    prev_id: Optional[UUID] = None
    limit: int = 1000
    ascending: bool = False


class InstanceCheck(CoreModel):
    reachable: bool
    message: Optional[str] = None
    health_response: Optional[InstanceHealthResponse] = None

    def get_health_status(self) -> HealthStatus:
        if self.health_response is None:
            return HealthStatus.HEALTHY
        if self.health_response.dcgm is None:
            return HealthStatus.HEALTHY
        return self.health_response.dcgm.overall_health.to_health_status()

    def has_health_checks(self) -> bool:
        if self.health_response is None:
            return False
        return self.health_response.dcgm is not None


class GetInstanceHealthChecksRequest(CoreModel):
    fleet_name: str
    instance_num: int
    after: Optional[datetime] = None
    before: Optional[datetime] = None
    limit: Optional[int] = None


class GetInstanceHealthChecksResponse(CoreModel):
    health_checks: list[HealthCheck]
