import json
import os.path
import re
import time
from collections import defaultdict
from pathlib import Path
from typing import Optional, Dict, List, Generator, Any, Tuple
from urllib import parse
from pygtail import Pygtail

from botocore.client import BaseClient

from dstack.backend.local import jobs, runs
from dstack.core.log_event import LogEvent, LogEventSource
from dstack.core.job import JobHead
from dstack.core.app import AppSpec
from dstack.core.repo import RepoAddress

WAIT_N_ONCE_FINISHED = 1

CHECK_STATUS_EVERY_N = 3

POLL_LOGS_RATE_SECS = 1

_events = []


def _render_log_message(
    path: str,
    event: Dict[str, Any],
    repo_address: RepoAddress,
    job_host_names: Dict[str, Optional[str]],
    job_ports: Dict[str, Optional[List[int]]],
    job_app_specs: Dict[str, Optional[List[AppSpec]]],
) -> LogEvent:
    message = event["message"]
    job_id = message["job_id"]
    log = message["log"]
    if job_id and job_id not in job_host_names:
        job = jobs.get_job(path, repo_address, job_id)
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
        event["eventId"],
        event["timestamp"],
        job_id,
        log,
        LogEventSource.STDOUT if message["source"] == "stdout" else LogEventSource.STDERR,
    )


def events_loop(path: str, repo_address: RepoAddress, job_heads: List[JobHead]):
    counter = 0
    finished_counter = 0
    tails = {}

    _jobs = [jobs.get_job(path, repo_address, job_head.job_id) for job_head in job_heads]
    for _job in _jobs:
        path_dir = (
            Path.home()
            / ".dstack"
            / "tmp"
            / "runner"
            / "configs"
            / _job.runner_id
            / "logs"
            / "jobs"
            / repo_address.path()
        )  # TODO Hardcode
        file_log = f"{_job.run_name}.log"  # TODO Hardcode
        if not path_dir.exists():
            path_dir.mkdir(parents=True)
            f = open(path_dir / file_log, "w")
            f.close()
        tails[_job.job_id] = Pygtail(
            os.path.join(path_dir, file_log), save_on_end=False, copytruncate=False
        )

    while True:
        if counter % CHECK_STATUS_EVERY_N == 0:
            _jobs = [jobs.get_job(path, repo_address, job_head.job_id) for job_head in job_heads]

            for _job in _jobs:
                for line_log in tails[_job.job_id]:
                    yield {
                        "message": {
                            "source": "stdout",
                            "log": line_log,
                            "job_id": _job.job_id,
                        },
                        "eventId": _job.runner_id,
                        "timestamp": time.time(),
                    }

            run = next(iter(runs.get_run_heads(path, _jobs, include_request_heads=False)))
            if run.status.is_finished():
                if finished_counter == WAIT_N_ONCE_FINISHED:
                    break
                finished_counter += 1
        counter = counter + 1
        time.sleep(POLL_LOGS_RATE_SECS)


def poll_logs(
    path: str,
    repo_address: RepoAddress,
    job_heads: List[JobHead],
    start_time: int,
    attached: bool,
) -> Generator[LogEvent, None, None]:
    job_host_names = {}
    job_ports = {}
    job_app_specs = {}
    try:
        # Read log_file
        for event in events_loop(path, repo_address, job_heads):
            yield _render_log_message(
                path, event, repo_address, job_host_names, job_ports, job_app_specs
            )
    except Exception as e:
        raise e
