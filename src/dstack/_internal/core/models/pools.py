import datetime
from typing import List, Optional

from pydantic import BaseModel

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import InstanceType
from dstack._internal.core.models.runs import InstanceStatus


class Pool(BaseModel):
    name: str
    default: bool
    created_at: datetime.datetime


class Instance(BaseModel):
    backend: BackendType
    instance_type: InstanceType
    instance_id: str
    hostname: str
    status: InstanceStatus
    price: float