from datetime import datetime
from typing import Optional

from pydantic import UUID4, Field, validator

from dstack._internal.core.models.common import CoreModel


class PollLogsRequest(CoreModel):
    run_name: str
    job_submission_id: UUID4
    start_time: Optional[datetime]
    end_time: Optional[datetime]
    descending: bool = False
    next_token: Optional[str] = None
    limit: int = Field(100, ge=0, le=1000)
    diagnose: bool = False

    @validator("descending")
    @classmethod
    def validate_descending(cls, v):
        # Descending is not supported until we migrate from base64-encoded logs to plain text logs.
        if v is True:
            raise ValueError("descending: true is not supported")
        return v
