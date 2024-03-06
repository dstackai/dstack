from datetime import datetime
from enum import Enum
from typing import List

from dstack._internal.core.models.common import CoreModel


class LogEventSource(str, Enum):
    STDOUT = "stdout"
    STDERR = "stderr"


class LogEvent(CoreModel):
    timestamp: datetime
    log_source: LogEventSource
    message: str


class JobSubmissionLogs(CoreModel):
    logs: List[LogEvent]
