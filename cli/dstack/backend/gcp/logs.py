import time
from typing import Generator, Optional

from google.cloud import logging
from google.oauth2 import service_account

from dstack.backend.base import jobs
from dstack.backend.base.logs import fix_urls
from dstack.backend.base.storage import Storage
from dstack.core.log_event import LogEvent, LogEventSource
from dstack.core.repo import RepoAddress

POLL_LOGS_ATTEMPTS = 5
POLL_LOGS_WAIT_TIME = 2


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
        repo_address: RepoAddress,
        run_name: str,
    ) -> Generator[LogEvent, None, None]:
        log_name = _get_log_name(self.bucket_name, repo_address, run_name)
        logger = self.logging_client.logger(log_name)
        # Hack: It takes some time for logs to become available after runner writes them.
        # So we try reading logs multiple times.
        # The proper solution would be for the runner to ensure logs availability before marking job as Done.
        found_log = False
        for _ in range(POLL_LOGS_ATTEMPTS):
            log_entries = logger.list_entries()
            for log_entry in log_entries:
                found_log = True
                yield _log_entry_to_log_event(storage, repo_address, log_entry)
            if found_log:
                break
            time.sleep(POLL_LOGS_WAIT_TIME)


def _get_log_name(bucket_name: str, repo_address: RepoAddress, run_name) -> str:
    return f"dstack-jobs-{bucket_name}-{repo_address.path('-')}-{run_name}"


def _log_entry_to_log_event(
    storage: Storage,
    repo_address: RepoAddress,
    log_entry: logging.LogEntry,
) -> LogEvent:
    job_id = log_entry.payload["job_id"]
    log = log_entry.payload["log"]
    job = jobs.get_job(storage, repo_address, job_id)
    log = fix_urls(log.encode(), job).decode()
    timestamp = int(log_entry.timestamp.timestamp())
    return LogEvent(
        event_id=log_entry.insert_id,
        timestamp=timestamp,
        job_id=job_id,
        log_message=log,
        log_source=LogEventSource.STDOUT
        if log_entry.payload["source"] == "stdout"
        else LogEventSource.STDERR,
    )
