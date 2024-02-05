import datetime

from pydantic import BaseModel

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import InstanceType
from dstack._internal.core.models.runs import InstanceStatus


class Pool(BaseModel):  # type: ignore[misc,valid-type]
    name: str
    default: bool
    created_at: datetime.datetime
    total_instances: int
    available_instances: int


class Instance(BaseModel):  # type: ignore[misc,valid-type]
    backend: BackendType
    instance_type: InstanceType
    instance_id: str
    hostname: str
    status: InstanceStatus
    price: float
