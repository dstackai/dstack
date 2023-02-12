import json
import re
from typing import Any, Dict, Generator, List, Optional, Tuple
from urllib import parse

from dstack.backend.base import jobs, runs
from dstack.backend.base.storage import Storage
from dstack.core.app import AppSpec
from dstack.core.job import JobHead
from dstack.core.log_event import LogEvent, LogEventSource
from dstack.core.repo import RepoAddress

WAIT_N_ONCE_FINISHED = 1

CHECK_STATUS_EVERY_N = 3

POLL_LOGS_RATE_SECS = 1


def render_log_message(
    storage: Storage,
    event: Dict[str, Any],
    repo_address: RepoAddress,
    job_host_names: Dict[str, Optional[str]],
    job_ports: Dict[str, Optional[List[int]]],
    job_app_specs: Dict[str, Optional[List[AppSpec]]],
) -> LogEvent:
    if isinstance(event, str):
        event = json.loads(event)
    message = event["message"]
    if isinstance(message, str):
        message = json.loads(message)
    job_id = message["job_id"]
    log = message["log"]
    if job_id and job_id not in job_host_names:
        job = jobs.get_job(storage, repo_address, job_id)
        job_host_names[job_id] = job.host_name or "none" if job else "none"
        job_ports[job_id] = job.ports if job else None
        job_app_specs[job_id] = job.app_specs if job else None
    host_name = job_host_names[job_id]
    ports = job_ports[job_id]
    app_specs = job_app_specs[job_id]
    pat = re.compile(f"http://(localhost|0.0.0.0|127.0.0.1|{host_name}):[\\S]*[^(.+)\\s\\n\\r]")
    if re.search(pat, log):
        if host_name != "none" and ports and app_specs:
            for app_spec in app_specs:
                port = ports[app_spec.port_index]
                url_path = app_spec.url_path or ""
                url_query_params = app_spec.url_query_params
                url_query = ("?" + parse.urlencode(url_query_params)) if url_query_params else ""
                app_url = f"http://{host_name}:{port}"
                if url_path or url_query_params:
                    app_url += "/"
                    if url_query_params:
                        app_url += url_query
                log = re.sub(pat, app_url, log)
    return LogEvent(
        event_id=event["eventId"],
        timestamp=event["timestamp"],
        job_id=job_id,
        log_message=log,
        log_source=LogEventSource.STDOUT if message["source"] == "stdout" else LogEventSource.STDERR,
    )
