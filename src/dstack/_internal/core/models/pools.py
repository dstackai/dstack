import datetime
from typing import List, Optional
from uuid import UUID

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.common import CoreModel
from dstack._internal.core.models.instances import InstanceStatus, InstanceType


class Pool(CoreModel):
    name: str
    default: bool
    created_at: datetime.datetime
    total_instances: int
    available_instances: int


class Instance(CoreModel):
    id: UUID
    project_name: str
    backend: Optional[BackendType] = None
    instance_type: Optional[InstanceType] = None
    name: str
    instance_num: int
    pool_name: Optional[str] = None
    job_name: Optional[str] = None
    hostname: Optional[str] = None
    status: InstanceStatus
    unreachable: bool = False
    created: datetime.datetime
    region: Optional[str] = None
    price: Optional[float] = None


class PoolInstances(CoreModel):
    name: str
    instances: List[Instance]
