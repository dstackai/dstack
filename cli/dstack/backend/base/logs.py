import json
import re
import urllib.parse
from typing import Any, Dict, Optional

from dstack.backend.base import jobs
from dstack.backend.base.storage import Storage
from dstack.core.job import Job
from dstack.core.log_event import LogEvent, LogEventSource

WAIT_N_ONCE_FINISHED = 1

CHECK_STATUS_EVERY_N = 3

POLL_LOGS_RATE_SECS = 1


def render_log_message(
    storage: Storage,
    event: Dict[str, Any],
    repo_id: str,
    jobs_cache: Dict[str, Job],
) -> LogEvent:
    if isinstance(event, str):
        event = json.loads(event)
    message = event["message"]
    if isinstance(message, str):
        message = json.loads(message)
    job_id = message["job_id"]
    log = message["log"]
    job = jobs_cache.get(job_id)
    if job is None:
        job = jobs.get_job(storage, repo_id, job_id)
        jobs_cache[job_id] = job
    log = fix_urls(log.encode(), job, {}).decode()
    return LogEvent(
        event_id=event["eventId"],
        timestamp=event["timestamp"],
        job_id=job_id,
        log_message=log,
        log_source=LogEventSource.STDOUT
        if message["source"] == "stdout"
        else LogEventSource.STDERR,
    )


def fix_urls(log: bytes, job: Job, ports: Dict[int, int], hostname: Optional[str] = None) -> bytes:
    if not (job.host_name and job.app_specs):
        return log

    hostname = hostname or job.host_name
    app_specs = {app_spec.port: app_spec for app_spec in job.app_specs}
    ports_re = "|".join(str(port) for port in app_specs.keys())
    url_pattern = rf"http://(?:localhost|0.0.0.0|127.0.0.1|{job.host_name}):({ports_re})\b([-a-zA-Z0-9()@:%_\+.~#?&//=]*)".encode()

    def replace_url(match: re.Match) -> bytes:
        remote_port = int(match.group(1))
        local_port = ports.get(remote_port, remote_port)
        app_spec = app_specs[remote_port]
        url = urllib.parse.urlparse(match.group(0))
        qs = {k: v[0] for k, v in urllib.parse.parse_qs(url.query).items()}
        if app_spec.url_query_params is not None:
            qs.update({k.encode(): v.encode() for k, v in app_spec.url_query_params.items()})
        url = url._replace(
            netloc=f"{hostname}:{local_port}".encode(), query=urllib.parse.urlencode(qs).encode()
        )
        return url.geturl()

    return re.sub(url_pattern, replace_url, log)
