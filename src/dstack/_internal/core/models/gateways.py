import datetime
from typing import Optional

from pydantic import BaseModel

from dstack._internal.core.models.backends.base import BackendType


class Gateway(BaseModel):
    name: str
    ip_address: str
    instance_id: str
    region: str
    wildcard_domain: Optional[str]
    default: bool
    created_at: datetime.datetime
    backend: BackendType
