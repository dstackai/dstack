from enum import Enum
from typing import Optional

from pydantic import BaseModel


class LogEventSource(Enum):
    STDOUT = "stdout"
    STDERR = "stderr"

    def __str__(self):
        return str(self.value)


class LogEvent(BaseModel):
    event_id: str
    timestamp: int
    job_id: Optional[str]
    log_message: str
    log_source: LogEventSource
