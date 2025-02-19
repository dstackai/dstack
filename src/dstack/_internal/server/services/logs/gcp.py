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


class GCPLogStorage(LogStorage):
    def __init__(self, project_id: str):
        self.client = logging.Client(project=project_id)

    def poll_logs(self, project: ProjectModel, request: PollLogsRequest) -> JobSubmissionLogs:
        producer = LogProducer.RUNNER if request.diagnose else LogProducer.JOB
        logger_name = self._get_logger_name(
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
    ) -> None:
        producers_with_logs = [(LogProducer.RUNNER, runner_logs), (LogProducer.JOB, job_logs)]
        for producer, producer_logs in producers_with_logs:
            logger_name = self._get_logger_name(
                project_name=project.name,
                run_name=run_name,
                job_submission_id=job_submission_id,
                producer=producer,
            )
            logger = self._get_logger(logger_name)
            for log in producer_logs:
                # TODO: log in batches
                logger.log_struct(
                    {
                        "message": b64encode_raw_message(log.message),
                    },
                    timestamp=unix_time_ms_to_datetime(log.timestamp),
                )

    def close(self) -> None:
        self.client.close()

    def _get_logger_name(
        self, project_name: str, run_name: str, job_submission_id: UUID, producer: LogProducer
    ) -> str:
        return f"{project_name}-{run_name}-{job_submission_id}-{producer.value}"

    def _get_logger(self, logger_name: str) -> logging.Logger:
        return logging.Logger(name=logger_name, client=self.client)
