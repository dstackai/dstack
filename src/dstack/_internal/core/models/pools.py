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
    backend: Optional[BackendType] = None
    instance_type: Optional[InstanceType] = None
    name: str
    job_name: Optional[str] = None
    job_status: Optional[JobStatus] = None
    hostname: Optional[str] = None
    status: InstanceStatus
    created: datetime.datetime
    region: Optional[str] = None
    price: Optional[float] = None


class PoolInstances(BaseModel):
    name: str
    instances: List[Instance]
