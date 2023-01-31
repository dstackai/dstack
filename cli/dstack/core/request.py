from enum import Enum
from typing import Optional


class RequestStatus(Enum):
    RUNNING = "fullfilled"
    PENDING = "provisioning"
    TERMINATED = "terminated"
    NO_CAPACITY = "no_capacity"


class RequestHead:
    def __init__(self, job_id: str, status: RequestStatus, message: Optional[str]):
        self.job_id = job_id
        self.status = status
        self.message = message

    def __str__(self) -> str:
        return (
            f'RequestStatus(job_id="{self.job_id}", status="{self.status.value}", '
            f'message="{self.message})'
        )
