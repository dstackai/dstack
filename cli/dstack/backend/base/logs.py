import json
import re
from typing import Any, Dict

from dstack.backend.base import jobs
from dstack.backend.base.storage import Storage
from dstack.core.job import Job
from dstack.core.log_event import LogEvent, LogEventSource
from dstack.core.repo import RepoAddress

WAIT_N_ONCE_FINISHED = 1

CHECK_STATUS_EVERY_N = 3

POLL_LOGS_RATE_SECS = 1


def render_log_message(
    storage: Storage,
    event: Dict[str, Any],
    repo_address: RepoAddress,
) -> LogEvent:
    if isinstance(event, str):
        event = json.loads(event)
    message = event["message"]
    if isinstance(message, str):
        message = json.loads(message)
    job_id = message["job_id"]
    log = message["log"]
    job = jobs.get_job(storage, repo_address, job_id)
    log = replace_logs_host(log, job)
    return LogEvent(
        event_id=event["eventId"],
        timestamp=event["timestamp"],
        job_id=job_id,
        log_message=log,
        log_source=LogEventSource.STDOUT
        if message["source"] == "stdout"
        else LogEventSource.STDERR,
    )


def replace_logs_host(log: str, job: Job) -> str:
    pat = get_logs_host_replace_pattern(job)
    sub = get_logs_host_replace_sub(job)
    if pat is not None:
        log = re.sub(pat, sub, log)
    return log


def get_logs_host_replace_pattern(job: str) -> str:
    if not (job.host_name and job.ports and job.app_specs):
        return None
    ports = []
    for app_spec in job.app_specs:
        ports.append(job.ports[app_spec.port_index])
    return (
        f"http://(localhost|0.0.0.0|127.0.0.1|{job.host_name}):"
        + "("
        + "|".join(str(p) for p in ports)
        + ")"
    )


def get_logs_host_replace_sub(job: str) -> str:
    return rf"http://{job.host_name}:\2"
