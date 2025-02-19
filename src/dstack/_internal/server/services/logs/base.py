import base64
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import List
from uuid import UUID

from dstack._internal.core.errors import DstackError
from dstack._internal.core.models.logs import JobSubmissionLogs
from dstack._internal.server.models import ProjectModel
from dstack._internal.server.schemas.logs import PollLogsRequest
from dstack._internal.server.schemas.runner import LogEvent as RunnerLogEvent


class LogStorageError(DstackError):
    pass


class LogStorage(ABC):
    @abstractmethod
    def poll_logs(self, project: ProjectModel, request: PollLogsRequest) -> JobSubmissionLogs:
        pass

    @abstractmethod
    def write_logs(
        self,
        project: ProjectModel,
        run_name: str,
        job_submission_id: UUID,
        runner_logs: List[RunnerLogEvent],
        job_logs: List[RunnerLogEvent],
    ) -> None:
        pass

    def close(self) -> None:
        pass


def unix_time_ms_to_datetime(unix_time_ms: int) -> datetime:
    return datetime.fromtimestamp(unix_time_ms / 1000, tz=timezone.utc)


def datetime_to_unix_time_ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def b64encode_raw_message(message: bytes) -> str:
    return base64.b64encode(message).decode()
