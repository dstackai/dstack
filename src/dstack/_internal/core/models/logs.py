from datetime import datetime
from enum import Enum
from typing import List

from pydantic import BaseModel


class LogEventSource(str, Enum):
    STDOUT = "stdout"
    STDERR = "stderr"


class LogEvent(BaseModel):
    timestamp: datetime
    log_source: LogEventSource
    message: str


class JobSubmissionLogs(BaseModel):
    logs: List[LogEvent]
