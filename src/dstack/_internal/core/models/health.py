from datetime import datetime
from enum import Enum

from dstack._internal.core.models.common import CoreModel


class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    WARNING = "warning"
    FAILURE = "failure"

    def is_healthy(self) -> bool:
        return self == self.HEALTHY

    def is_failure(self) -> bool:
        return self == self.FAILURE


class HealthEvent(CoreModel):
    timestamp: datetime
    status: HealthStatus
    message: str


class HealthCheck(CoreModel):
    collected_at: datetime
    status: HealthStatus
    events: list[HealthEvent]
