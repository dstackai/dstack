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

    def __str__(self) -> str:
        return (
            f'RequestStatus(job_id="{self.job_id}", status="{self.status.value}", '
            f'message="{self.message})'
        )
