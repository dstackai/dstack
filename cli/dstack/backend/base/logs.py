import json
import re
import urllib.parse
from typing import Any, Dict, List

from dstack.backend.base import jobs
from dstack.backend.base.storage import Storage
from dstack.core.app import AppSpec
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
    log = fix_urls(log.encode(), job).decode()
    return LogEvent(
        event_id=event["eventId"],
        timestamp=event["timestamp"],
        job_id=job_id,
        log_message=log,
        log_source=LogEventSource.STDOUT
        if message["source"] == "stdout"
        else LogEventSource.STDERR,
    )


def fix_urls(log: bytes, job: Job) -> bytes:
    if not (job.host_name and job.ports and job.app_specs):
        return log
    for app_spec in job.app_specs:
        log = _fix_url_for_app(log, job, app_spec)
    return log


def _fix_url_for_app(log: bytes, job: Job, app_spec: AppSpec) -> bytes:
    port = job.ports[app_spec.port_index]
    url_pattern = f"http://(localhost|0.0.0.0|127.0.0.1|{job.host_name}):{port}\S*".encode()
    match = re.search(url_pattern, log)
    if match is None:
        return log
    url = match.group(0)
    parsed_url = urllib.parse.urlparse(url)
    qs = urllib.parse.parse_qs(parsed_url.query)
    qs = {k: v[0] for k, v in qs.items()}
    if app_spec.url_query_params is not None:
        for k, v in app_spec.url_query_params.items():
            qs[k.encode()] = v.encode()
    new_url = parsed_url._replace(
        netloc=f"{job.host_name}:{port}".encode(), query=urllib.parse.urlencode(qs).encode()
    ).geturl()
    return log.replace(url, new_url)
