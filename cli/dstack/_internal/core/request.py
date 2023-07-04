from enum import Enum
from typing import Optional

from pydantic import BaseModel


class RequestStatus(Enum):
    RUNNING = "fullfilled"
    PENDING = "provisioning"
    TERMINATED = "terminated"
    NO_CAPACITY = "no_capacity"


class RequestHead(BaseModel):
    job_id: str
    status: RequestStatus
    message: Optional[str]
