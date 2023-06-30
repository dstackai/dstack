from datetime import datetime
from typing import Dict, Generator, Optional

from google.cloud import logging
from google.oauth2 import service_account

from dstack._internal.backend.base import jobs as base_jobs
from dstack._internal.backend.base.logs import Logging, fix_log_event_urls
from dstack._internal.backend.base.storage import Storage
from dstack._internal.core.job import Job
from dstack._internal.core.log_event import LogEvent, LogEventSource

LOGS_TIME_FORMAT = "%Y-%m-%dT%H:%M:%S.%f%z"


class GCPLogging(Logging):
    def __init__(
        self, project_id: str, bucket_name: str, credentials: Optional[service_account.Credentials]
    ):
        self.project_id = project_id
        self.bucket_name = bucket_name
        self.logging_client = logging.Client(project=project_id, credentials=credentials)

    def poll_logs(
        self,
        storage: Storage,
        repo_id: str,
        run_name: str,
        start_time: datetime,
        end_time: Optional[datetime],
        descending: bool,
        diagnose: bool,
    ) -> Generator[LogEvent, None, None]:
        jobs = base_jobs.list_jobs(storage, repo_id, run_name)
        jobs_map = {j.job_id: j for j in jobs}
        if diagnose:
            runner_id = jobs[0].runner_id
            log_name = _get_runners_log_name(self.bucket_name, runner_id)
        else:
            log_name = _get_jobs_log_name(self.bucket_name, repo_id, run_name)

        timestamp_from = start_time.strftime(LOGS_TIME_FORMAT)
        filter = f'timestamp>="{timestamp_from}"'
        if end_time is not None:
            end_time_limit = end_time.replace(microsecond=end_time.microsecond + 1)
            timestamp_to = end_time_limit.strftime(LOGS_TIME_FORMAT)
            filter += f' AND timestamp<="{timestamp_to}"'

        order_by = logging.ASCENDING
        if descending:
            order_by = logging.DESCENDING

        logger = self.logging_client.logger(log_name)
        log_entries = logger.list_entries(filter_=filter, order_by=order_by)
        for log_entry in log_entries:
            log_event = _log_entry_to_log_event(log_entry)
            if not diagnose:
                log_event = fix_log_event_urls(log_event, jobs_map)
            yield log_event


def _get_jobs_log_name(bucket_name: str, repo_id: str, run_name) -> str:
    return f"dstack-jobs-{bucket_name}-{repo_id}-{run_name}"


def _get_runners_log_name(bucket_name: str, runner_id: str) -> str:
    return f"dstack-runners-{bucket_name}-{runner_id}"


def _log_entry_to_log_event(
    log_entry: logging.LogEntry,
) -> LogEvent:
    job_id = log_entry.payload["job_id"]
    log = log_entry.payload["log"]
    timestamp = log_entry.timestamp
    return LogEvent(
        event_id=log_entry.insert_id,
        timestamp=timestamp,
        job_id=job_id,
        log_message=log,
        log_source=LogEventSource.STDOUT
        if log_entry.payload["source"] == "stdout"
        else LogEventSource.STDERR,
    )
