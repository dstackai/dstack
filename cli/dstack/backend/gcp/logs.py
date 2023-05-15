from datetime import datetime
from typing import Dict, Generator, Optional

from google.cloud import logging
from google.oauth2 import service_account

from dstack.backend.base import jobs
from dstack.backend.base.logs import fix_urls
from dstack.backend.base.storage import Storage
from dstack.core.job import Job
from dstack.core.log_event import LogEvent, LogEventSource

LOGS_TIME_FORMAT = "%Y-%m-%dT%H:%M:%S.%f%z"


class GCPLogging:
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
    ) -> Generator[LogEvent, None, None]:
        log_name = _get_log_name(self.bucket_name, repo_id, run_name)

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
        jobs_cache = {}
        log_entries = logger.list_entries(filter_=filter, order_by=order_by)
        for log_entry in log_entries:
            yield _log_entry_to_log_event(storage, repo_id, log_entry, jobs_cache)


def _get_log_name(bucket_name: str, repo_id: str, run_name) -> str:
    return f"dstack-jobs-{bucket_name}-{repo_id}-{run_name}"


def _log_entry_to_log_event(
    storage: Storage,
    repo_id: str,
    log_entry: logging.LogEntry,
    jobs_cache: Dict[str, Job],
) -> LogEvent:
    job_id = log_entry.payload["job_id"]
    log = log_entry.payload["log"]
    job = jobs_cache.get(job_id)
    if job is None:
        job = jobs.get_job(storage, repo_id, job_id)
        jobs_cache[job_id] = job
    log = fix_urls(log.encode(), job, {}).decode()
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
