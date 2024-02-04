import datetime

from pydantic import BaseModel

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import InstanceType
from dstack._internal.core.models.runs import InstanceStatus


class Pool(BaseModel):  # type: ignore[misc]
    name: str
    default: bool
    created_at: datetime.datetime


class Instance(BaseModel):  # type: ignore[misc]
    backend: BackendType
    instance_type: InstanceType
    instance_id: str
    hostname: str
    status: InstanceStatus
    price: float
