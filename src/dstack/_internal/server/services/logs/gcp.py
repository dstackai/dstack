from typing import List
from uuid import UUID

from google.cloud import logging

from dstack._internal.core.models.logs import (
    JobSubmissionLogs,
    LogEvent,
    LogEventSource,
    LogProducer,
)
from dstack._internal.server.models import ProjectModel
from dstack._internal.server.schemas.logs import PollLogsRequest
from dstack._internal.server.schemas.runner import LogEvent as RunnerLogEvent
from dstack._internal.server.services.logs.base import (
    LogStorage,
    b64encode_raw_message,
    unix_time_ms_to_datetime,
)
from dstack._internal.utils.common import batched
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


class GCPLogStorage(LogStorage):
    # Max expected message size from runner is 32KB.
    # Max expected LogEntry size is 32KB + metadata < 50KB < 256KB limit.
    # With MAX_BATCH_SIZE = 100, max write request size < 5MB < 10 MB limit.
    # See: https://cloud.google.com/logging/quotas.
    MAX_RUNNER_MESSAGE_SIZE = 32**20**2
    MAX_BATCH_SIZE = 100

    def __init__(self, project_id: str):
        self.client = logging.Client(project=project_id)

    def poll_logs(self, project: ProjectModel, request: PollLogsRequest) -> JobSubmissionLogs:
        producer = LogProducer.RUNNER if request.diagnose else LogProducer.JOB
        logger_name = self._get_gcp_logger_name(
            project_name=project.name,
            run_name=request.run_name,
            job_submission_id=request.job_submission_id,
            producer=producer,
        )
        log_filter = f'logName="projects/{self.client.project}/logs/{logger_name}"'
        if request.start_time:
            log_filter += f' AND timestamp > "{request.start_time.isoformat()}"'
        if request.end_time:
            log_filter += f' AND timestamp < "{request.end_time.isoformat()}"'

        order_by = logging.DESCENDING if request.descending else logging.ASCENDING

        entries: List[logging.LogEntry] = list(
            self.client.list_entries(
                filter_=log_filter,
                order_by=order_by,
                max_results=request.limit,
            )
        )
        logs = [
            LogEvent(
                timestamp=entry.timestamp,
                message=entry.payload["message"],
                log_source=LogEventSource.STDOUT,
            )
            for entry in entries
        ]
        return JobSubmissionLogs(logs=logs)

    def write_logs(
        self,
        project: ProjectModel,
        run_name: str,
        job_submission_id: UUID,
        runner_logs: List[RunnerLogEvent],
        job_logs: List[RunnerLogEvent],
    ):
        producers_with_logs = [(LogProducer.RUNNER, runner_logs), (LogProducer.JOB, job_logs)]
        for producer, producer_logs in producers_with_logs:
            gcp_logger_name = self._get_gcp_logger_name(
                project_name=project.name,
                run_name=run_name,
                job_submission_id=job_submission_id,
                producer=producer,
            )
            gcp_logger = self._get_gcp_logger(gcp_logger_name)
            self._write_logs_with_logger(gcp_logger, producer_logs)

    def _write_logs_with_logger(self, gcp_logger: logging.Logger, logs: List[RunnerLogEvent]):
        with gcp_logger.batch() as batcher:
            for batch in batched(logs, self.MAX_BATCH_SIZE):
                for log in logs:
                    message = b64encode_raw_message(log.message)
                    timestamp = unix_time_ms_to_datetime(log.timestamp)
                    # as message is base64-encoded, length in bytes = length in code points
                    if len(message) > self.MAX_RUNNER_MESSAGE_SIZE:
                        logger.error(
                            "Logger %s: skipping event %d, message exceeds max size: %d > %d",
                            gcp_logger.name,
                            timestamp,
                            len(message),
                            self.MAX_RUNNER_MESSAGE_SIZE,
                        )
                        continue
                    batcher.log_struct(
                        {
                            "message": message,
                        },
                        timestamp=timestamp,
                    )
                batcher.commit()

    def close(self):
        self.client.close()

    def _get_gcp_logger_name(
        self, project_name: str, run_name: str, job_submission_id: UUID, producer: LogProducer
    ) -> str:
        return f"{project_name}-{run_name}-{job_submission_id}-{producer.value}"

    def _get_gcp_logger(self, logger_name: str) -> logging.Logger:
        return logging.Logger(name=logger_name, client=self.client)
