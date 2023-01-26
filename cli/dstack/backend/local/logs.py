import json
import re
import time
from collections import defaultdict
from typing import Optional, Dict, List, Generator, Any, Tuple
from urllib import parse

from botocore.client import BaseClient

from dstack.backend.local import jobs, runs
from dstack.core.log_event import LogEvent, LogEventSource
from dstack.core.job import JobHead
from dstack.core.app import AppSpec
from dstack.core.repo import RepoAddress

WAIT_N_ONCE_FINISHED = 1

CHECK_STATUS_EVERY_N = 3

POLL_LOGS_RATE_SECS = 1


def _render_log_message(path: str, event: Dict[str, Any],
                        repo_address: RepoAddress,
                        job_host_names: Dict[str, Optional[str]],
                        job_ports: Dict[str, Optional[List[int]]],
                        job_app_specs: Dict[str, Optional[List[AppSpec]]]) -> LogEvent:
    message = json.loads(event["message"].strip())
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
    pat = re.compile(f'http://(localhost|0.0.0.0|127.0.0.1|{host_name}):[\\S]*[^(.+)\\s\\n\\r]')
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
    return LogEvent(event["eventId"], event["timestamp"], job_id, log,
                    LogEventSource.STDOUT if message["source"] == "stdout" else LogEventSource.STDERR)


def _get_latest_events_and_timestamp(event_ids_per_timestamp):
    if event_ids_per_timestamp:
        newest_timestamp = max(event_ids_per_timestamp.keys())
        event_ids_per_timestamp = defaultdict(
            set, {newest_timestamp: event_ids_per_timestamp[newest_timestamp]}
        )
    return event_ids_per_timestamp


def _reset_filter_log_events_params(fle_kwargs, event_ids_per_timestamp):
    if event_ids_per_timestamp:
        fle_kwargs['startTime'] = max(
            event_ids_per_timestamp.keys()
        )
    fle_kwargs.pop('nextToken', None)


def _filter_log_events_loop(path: str,
                            repo_address: RepoAddress, job_heads: List[JobHead],
                            filter_logs_events_kwargs: dict):
    pass


def create_log_group_if_not_exists(path: str, log_group_name: str):
    pass


def create_log_stream(logs_client: BaseClient, log_group_name: str, run_name: str):
    pass


def _filter_logs_events_kwargs(bucket_name: str, repo_address: RepoAddress, run_name: str, start_time: int,
                               end_time: Optional[int], next_token: Optional[str]):
    pass

def poll_logs(path: str,
              repo_address: RepoAddress, job_heads: List[JobHead], start_time: int, attached: bool) \
        -> Generator[LogEvent, None, None]:
    try:
        yield LogEvent("", "", "job_id", "log", LogEventSource.STDOUT)
    except Exception as e:
        raise e


def query_logs(path: str,
               repo_address: RepoAddress, run_name: str, start_time: int, end_time: Optional[int],
               next_token: Optional[str],
               job_host_names: Dict[str, Optional[str]], job_ports: Dict[str, Optional[List[int]]],
               job_app_specs: Dict[str, Optional[List[AppSpec]]]) -> Tuple[List[LogEvent], Optional[str],
Dict[str, Optional[str]],
Dict[str, Optional[List[int]]],
Dict[str, Optional[List[AppSpec]]]]:
    job_host_names = dict(job_host_names)
    job_ports = dict(job_ports)
    job_app_specs = dict(job_app_specs)
    filter_logs_events_kwargs = _filter_logs_events_kwargs(path, repo_address, run_name, start_time,
                                                           end_time, next_token)
    response = []
    return [_render_log_message(path, event, repo_address, job_host_names, job_ports,
                                job_app_specs)
            for event in response], response.get("nextToken"), job_host_names, job_ports, job_app_specs


def get_paginator():
    return []

