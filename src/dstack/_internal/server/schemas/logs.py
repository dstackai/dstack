from datetime import datetime
from typing import Optional

from pydantic import UUID4, Field

from dstack._internal.core.models.common import CoreModel


class PollLogsRequest(CoreModel):
    run_name: str
    job_submission_id: UUID4
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    descending: bool = False
    next_token: Optional[str] = None
    limit: int = Field(100, ge=0, le=1000)
    diagnose: bool = False
