from typing import Optional
from enum import Enum


class LogEventSource(Enum):
    STDOUT = "stdout"
    STDERR = "stderr"

    def __str__(self):
        return str(self.value)


class LogEvent:
    def __init__(
        self,
        event_id: str,
        timestamp: int,
        job_id: Optional[str],
        log_message: str,
        log_source: LogEventSource,
    ):
        self.event_id = event_id
        self.timestamp = timestamp
        self.job_id = job_id
        self.log_message = log_message
        self.log_source = log_source
