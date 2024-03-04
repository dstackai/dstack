import datetime
from typing import List, Optional

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.common import CoreModel
from dstack._internal.core.models.instances import InstanceType
from dstack._internal.core.models.runs import InstanceStatus, JobStatus


class Pool(CoreModel):
    name: str
    default: bool
    created_at: datetime.datetime
    total_instances: int
    available_instances: int


class Instance(CoreModel):
    backend: BackendType
    instance_type: InstanceType
    name: str
    job_name: Optional[str] = None
    job_status: Optional[JobStatus] = None
    hostname: str
    status: InstanceStatus
    created: datetime.datetime
    region: str
    price: float


class PoolInstances(CoreModel):
    name: str
    instances: List[Instance]
