from datetime import datetime
from enum import Enum
from typing import List, Optional

from dstack._internal.core.models.common import CoreModel


class LogProducer(Enum):
    RUNNER = "runner"
    JOB = "job"


class LogEventSource(str, Enum):
    STDOUT = "stdout"
    STDERR = "stderr"


class LogEvent(CoreModel):
    timestamp: datetime
    log_source: LogEventSource
    message: str


class JobSubmissionLogs(CoreModel):
    logs: List[LogEvent]
    external_url: Optional[str] = None
    next_token: Optional[str] = None
