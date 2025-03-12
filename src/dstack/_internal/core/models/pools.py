import datetime
from typing import Optional
from uuid import UUID

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.common import CoreModel
from dstack._internal.core.models.instances import InstanceStatus, InstanceType


class Instance(CoreModel):
    id: UUID
    project_name: str
    backend: Optional[BackendType] = None
    instance_type: Optional[InstanceType] = None
    name: str
    fleet_id: Optional[UUID] = None
    fleet_name: Optional[str] = None
    instance_num: int
    job_name: Optional[str] = None  # deprecated, always None (instance can have more than one job)
    hostname: Optional[str] = None
    status: InstanceStatus
    unreachable: bool = False
    termination_reason: Optional[str] = None
    created: datetime.datetime
    region: Optional[str] = None
    availability_zone: Optional[str] = None
    price: Optional[float] = None
    total_blocks: Optional[int] = None
    busy_blocks: int = 0
