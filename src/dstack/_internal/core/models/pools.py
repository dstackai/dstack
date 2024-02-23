import datetime
from typing import List, Optional

from pydantic import BaseModel

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import InstanceType
from dstack._internal.core.models.runs import InstanceStatus, JobStatus


class Pool(BaseModel):
    name: str
    default: bool
    created_at: datetime.datetime
    total_instances: int
    available_instances: int


class Instance(BaseModel):
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


class PoolInstances(BaseModel):
    name: str
    instances: List[Instance]
