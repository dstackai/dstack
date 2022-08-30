import json
import re
import time
from collections import defaultdict
from typing import Optional, Dict, List, Generator, Any
from urllib import parse

from botocore.client import BaseClient

from dstack.aws import jobs, runs
from dstack.backend import LogEvent, LogEventSource
from dstack.jobs import AppSpec, JobHead

POLL_LOGS_RATE_SECS = 1


def _render_log_message(s3_client: BaseClient, bucket_name: str, event: Dict[str, Any],
                        repo_user_name: str, repo_name: str,
                        job_host_names: Dict[str, Optional[str]],
                        job_ports: Dict[str, Optional[List[int]]],
                        job_app_specs: Dict[str, Optional[List[AppSpec]]]) -> LogEvent:
    message = json.loads(event["message"].strip())
    job_id = message["job_id"]
    log = message["log"]
    if job_id and job_id not in job_host_names:
        job = jobs.get_job(s3_client, bucket_name, repo_user_name, repo_name, job_id)
        job_host_names[job_id] = job.host_name or "none" if job else "none"
        job_ports[job_id] = job.ports if job else None
        job_app_specs[job_id] = job.app_specs if job else None
    host_name = job_host_names[job_id]
    ports = job_ports[job_id]
    app_specs = job_app_specs[job_id]
    pat = re.compile(f'http://(localhost|0.0.0.0|{host_name}):[\\S]*[^(.+)\\s\\n\\r]')
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
    return LogEvent(event["timestamp"], job_id, log,
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


def _filter_log_events_loop(ec2_client: BaseClient, s3_client: BaseClient, logs_client: BaseClient, bucket_name: str,
                            repo_user_name: str, repo_name: str, job_heads: List[JobHead],
                            filter_logs_events_kwargs: dict):
    event_ids_per_timestamp = defaultdict(set)
    counter = 0
    while True:
        response = logs_client.filter_log_events(**filter_logs_events_kwargs)

        for event in response["events"]:
            if event["eventId"] not in event_ids_per_timestamp[event["timestamp"]]:
                event_ids_per_timestamp[event["timestamp"]].add(event["eventId"])
                yield event
        event_ids_per_timestamp = _get_latest_events_and_timestamp(
            event_ids_per_timestamp
        )
        if "nextToken" in response:
            filter_logs_events_kwargs["nextToken"] = response["nextToken"]
        else:
            _reset_filter_log_events_params(
                filter_logs_events_kwargs,
                event_ids_per_timestamp
            )
            time.sleep(POLL_LOGS_RATE_SECS)
            counter = counter + 1
            if counter % 3 == 0:
                run = next(iter(runs.get_run_heads(ec2_client, s3_client, bucket_name, repo_user_name, repo_name,
                                                   job_heads, include_request_heads=False)))
                if run.status.is_finished():
                    break


def create_log_group_if_not_exists(logs_client: BaseClient, bucket_name: str, log_group_name: str):
    response = logs_client.describe_log_groups(logGroupNamePrefix=log_group_name)
    if not response["logGroups"] or not any(
            filter(lambda g: g["logGroupName"] == log_group_name, response["logGroups"])):
        logs_client.create_log_group(
            logGroupName=log_group_name,
            tags={
                'owner': 'dstack',
                'dstack_bucket': bucket_name,
            }
        )


def create_log_stream(logs_client: BaseClient, log_group_name: str, run_name: str):
    logs_client.create_log_stream(logGroupName=log_group_name, logStreamName=run_name)


def poll_logs(ec2_client: BaseClient, s3_client: BaseClient, logs_client: BaseClient, bucket_name: str,
              repo_user_name: str, repo_name: str,
              job_heads: List[JobHead], start_time: int, attached: bool) -> Generator[LogEvent, None, None]:
    run_name = job_heads[0].run_name
    filter_logs_events_kwargs = {
        "logGroupName": f"/dstack/jobs/{bucket_name}/{repo_user_name}/{repo_name}",
        "logStreamNames": [run_name],
        "startTime": start_time,
        "interleaved": True,
    }
    job_host_names = {}
    job_ports = {}
    job_app_specs = {}

    try:
        if attached:
            for event in _filter_log_events_loop(ec2_client, s3_client, logs_client, bucket_name, repo_user_name,
                                                 repo_name, job_heads, filter_logs_events_kwargs):
                yield _render_log_message(s3_client, bucket_name, event, repo_user_name, repo_name,
                                          job_host_names, job_ports, job_app_specs)
        else:
            paginator = logs_client.get_paginator("filter_log_events")
            for page in paginator.paginate(**filter_logs_events_kwargs):
                for event in page["events"]:
                    yield _render_log_message(s3_client, bucket_name, event, repo_user_name,
                                              repo_name, job_host_names, job_ports, job_app_specs)
    except Exception as e:
        if hasattr(e, "response") and e.response.get("Error") and e.response["Error"].get(
                "Code") == "ResourceNotFoundException":
            return
        else:
            raise e
