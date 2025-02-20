import time
from typing import Iterable, List
from uuid import UUID

from dstack._internal.core.errors import ServerClientError
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
    LogStorageError,
    b64encode_raw_message,
    unix_time_ms_to_datetime,
)
from dstack._internal.utils.common import batched
from dstack._internal.utils.logging import get_logger

GCP_LOGGING_AVAILABLE = True
try:
    import google.api_core.exceptions
    import google.auth.exceptions
    from google.cloud import logging
except ImportError:
    GCP_LOGGING_AVAILABLE = False


logger = get_logger(__name__)


class GCPLogStorage(LogStorage):
    # Max expected message size from runner is 32KB.
    # Max expected LogEntry size is 32KB + metadata < 50KB < 256KB limit.
    # With MAX_BATCH_SIZE = 100, max write request size < 5MB < 10 MB limit.
    # See: https://cloud.google.com/logging/quotas.
    MAX_RUNNER_MESSAGE_SIZE = 32 * 1024
    MAX_BATCH_SIZE = 100

    # Use the same log name for all run logs so that it's easy to manage all dstack-related logs.
    LOG_NAME = "dstack-run-logs"
    # Logs from different jobs belong to different "streams".
    # GCP Logging has no built-in concepts of streams, so we implement them with labels.
    # It should be fast to filter by labels since labels are indexed by default
    # (https://cloud.google.com/logging/docs/analyze/custom-index).

    def __init__(self, project_id: str):
        try:
            self.client = logging.Client(project=project_id)
            self.logger = self.client.logger(name=self.LOG_NAME)
            self.logger.list_entries(max_results=1)
            # Python client doesn't seem to support dry_run,
            # so emit an empty log to check permissions.
            self.logger.log_empty()
        except google.auth.exceptions.DefaultCredentialsError:
            raise LogStorageError("Default credentials not found")
        except google.api_core.exceptions.NotFound:
            raise LogStorageError(f"Project {project_id} not found")
        except google.api_core.exceptions.PermissionDenied:
            raise LogStorageError("Insufficient permissions")

    def poll_logs(self, project: ProjectModel, request: PollLogsRequest) -> JobSubmissionLogs:
        producer = LogProducer.RUNNER if request.diagnose else LogProducer.JOB
        stream_name = self._get_stream_name(
            project_name=project.name,
            run_name=request.run_name,
            job_submission_id=request.job_submission_id,
            producer=producer,
        )
        log_filters = [f'labels.stream = "{stream_name}"']
        if request.start_time:
            log_filters.append(f'timestamp > "{request.start_time.isoformat()}"')
        if request.end_time:
            log_filters.append(f'timestamp < "{request.end_time.isoformat()}"')
        log_filter = " AND ".join(log_filters)

        order_by = logging.DESCENDING if request.descending else logging.ASCENDING
        try:
            entries: Iterable[logging.LogEntry] = self.logger.list_entries(
                filter_=log_filter,
                order_by=order_by,
                max_results=request.limit,
                # Specify max possible page_size (<=1000) to reduce number of API calls.
                page_size=request.limit,
            )
            logs = [
                LogEvent(
                    timestamp=entry.timestamp,
                    message=entry.payload["message"],
                    log_source=LogEventSource.STDOUT,
                )
                for entry in entries
            ]
        except google.api_core.exceptions.ResourceExhausted as e:
            logger.warning("GCP Logging exception: %s", repr(e))
            # GCP Logging has severely low quota of 60 reads/min for entries.list
            raise ServerClientError(
                "GCP Logging read request limit exceeded."
                " It's recommended to increase default entries.list request quota from 60 per minute."
            )
        # We intentionally make reading logs slow to prevent hitting GCP quota.
        # This doesn't help with many concurrent clients but
        # should help with one client reading all logs sequentially.
        time.sleep(1)
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
            stream_name = self._get_stream_name(
                project_name=project.name,
                run_name=run_name,
                job_submission_id=job_submission_id,
                producer=producer,
            )
            self._write_logs_to_stream(
                stream_name=stream_name,
                logs=producer_logs,
            )

    def close(self):
        self.client.close()

    def _write_logs_to_stream(self, stream_name: str, logs: List[RunnerLogEvent]):
        with self.logger.batch() as batcher:
            for batch in batched(logs, self.MAX_BATCH_SIZE):
                for log in batch:
                    message = b64encode_raw_message(log.message)
                    timestamp = unix_time_ms_to_datetime(log.timestamp)
                    # as message is base64-encoded, length in bytes = length in code points
                    if len(message) > self.MAX_RUNNER_MESSAGE_SIZE:
                        logger.error(
                            "Stream %s: skipping event at %s, message exceeds max size: %d > %d",
                            stream_name,
                            timestamp.isoformat(),
                            len(message),
                            self.MAX_RUNNER_MESSAGE_SIZE,
                        )
                        continue
                    batcher.log_struct(
                        {
                            "message": message,
                        },
                        labels={
                            "stream": stream_name,
                        },
                        timestamp=timestamp,
                    )
                batcher.commit()

    def _get_stream_name(
        self, project_name: str, run_name: str, job_submission_id: UUID, producer: LogProducer
    ) -> str:
        return f"{project_name}-{run_name}-{job_submission_id}-{producer.value}"
