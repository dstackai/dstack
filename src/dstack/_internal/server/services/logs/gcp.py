import urllib.parse
from typing import List
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
    unix_time_ms_to_datetime,
)
from dstack._internal.utils.common import batched
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


GCP_LOGGING_AVAILABLE = True
try:
    import google.api_core.exceptions
    import google.auth.exceptions
    from google.cloud import logging_v2
    from google.cloud.logging_v2.types import ListLogEntriesRequest
except ImportError:
    GCP_LOGGING_AVAILABLE = False
else:

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
            self.project_id = project_id
            try:
                self.client = logging_v2.Client(project=project_id)
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
            # TODO: GCP may return logs in random order when events have the same timestamp.
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

            order_by = logging_v2.DESCENDING if request.descending else logging_v2.ASCENDING
            try:
                # Use low-level API to get access to next_page_token
                request_obj = ListLogEntriesRequest(
                    resource_names=[f"projects/{self.client.project}"],
                    filter=log_filter,
                    order_by=order_by,
                    page_size=request.limit,
                    page_token=request.next_token,
                )
                response = self.client._logging_api._gapic_api.list_log_entries(  # type: ignore[attr-defined]
                    request=request_obj
                )

                logs = [
                    LogEvent(
                        timestamp=entry.timestamp,
                        message=entry.json_payload.get("message"),
                        log_source=LogEventSource.STDOUT,
                    )
                    for entry in response.entries
                ]
                next_token = response.next_page_token or None
            except google.api_core.exceptions.ResourceExhausted as e:
                logger.warning("GCP Logging exception: %s", repr(e))
                # GCP Logging has severely low quota of 60 reads/min for entries.list
                raise ServerClientError(
                    "GCP Logging read request limit exceeded."
                    " It's recommended to increase default entries.list request quota from 60 per minute."
                )
            return JobSubmissionLogs(
                logs=logs,
                external_url=self._get_stream_extrnal_url(stream_name),
                next_token=next_token if len(logs) > 0 else None,
            )

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
                        message = log.message.decode(errors="replace")
                        timestamp = unix_time_ms_to_datetime(log.timestamp)
                        if len(log.message) > self.MAX_RUNNER_MESSAGE_SIZE:
                            logger.error(
                                "Stream %s: skipping event at %s, message exceeds max size: %d > %d",
                                stream_name,
                                timestamp.isoformat(),
                                len(log.message),
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

        def _get_stream_extrnal_url(self, stream_name: str) -> str:
            log_name_resource_name = self._get_log_name_resource_name()
            query = f'logName="{log_name_resource_name}" AND labels.stream="{stream_name}"'
            quoted_query = urllib.parse.quote(query, safe="")
            return f"https://console.cloud.google.com/logs/query;query={quoted_query}?project={self.project_id}"

        def _get_log_name_resource_name(self) -> str:
            return f"projects/{self.project_id}/logs/{self.LOG_NAME}"
