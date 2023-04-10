import time
from collections import defaultdict
from typing import Generator, List, Optional, Tuple

from botocore.client import BaseClient

from dstack.backend.base import jobs, runs
from dstack.backend.base.compute import Compute
from dstack.backend.base.logs import render_log_message
from dstack.backend.base.storage import Storage
from dstack.core.job import JobHead
from dstack.core.log_event import LogEvent, LogEventSource
from dstack.core.repo import RepoAddress

WAIT_N_ONCE_FINISHED = 1

CHECK_STATUS_EVERY_N = 3

POLL_LOGS_RATE_SECS = 1


def _get_latest_events_and_timestamp(event_ids_per_timestamp):
    if event_ids_per_timestamp:
        newest_timestamp = max(event_ids_per_timestamp.keys())
        event_ids_per_timestamp = defaultdict(
            set, {newest_timestamp: event_ids_per_timestamp[newest_timestamp]}
        )
    return event_ids_per_timestamp


def _reset_filter_log_events_params(fle_kwargs, event_ids_per_timestamp):
    if event_ids_per_timestamp:
        fle_kwargs["startTime"] = max(event_ids_per_timestamp.keys())
    fle_kwargs.pop("nextToken", None)


def _filter_log_events_loop(
    storage: Storage,
    compute: Compute,
    logs_client: BaseClient,
    repo_address: RepoAddress,
    job_heads: List[JobHead],
    filter_logs_events_kwargs: dict,
):
    event_ids_per_timestamp = defaultdict(set)
    counter = 0
    finished_counter = 0
    while True:
        response = logs_client.filter_log_events(**filter_logs_events_kwargs)
        for event in response["events"]:
            if event["eventId"] not in event_ids_per_timestamp[event["timestamp"]]:
                event_ids_per_timestamp[event["timestamp"]].add(event["eventId"])
                yield event
        event_ids_per_timestamp = _get_latest_events_and_timestamp(event_ids_per_timestamp)
        if "nextToken" in response:
            filter_logs_events_kwargs["nextToken"] = response["nextToken"]
        else:
            _reset_filter_log_events_params(filter_logs_events_kwargs, event_ids_per_timestamp)
            time.sleep(POLL_LOGS_RATE_SECS)
            counter = counter + 1
            if counter % CHECK_STATUS_EVERY_N == 0:
                _job_heads = [
                    jobs.get_job(storage, repo_address, job_head.job_id) for job_head in job_heads
                ]
                run = next(
                    iter(
                        runs.get_run_heads(
                            storage, compute, _job_heads, include_request_heads=False
                        )
                    )
                )
                if run.status.is_finished():
                    if finished_counter == WAIT_N_ONCE_FINISHED:
                        break
                    finished_counter += 1


def create_log_group_if_not_exists(
    logs_client: BaseClient, bucket_name: str, repo_address: RepoAddress
):
    log_group_name = f"/dstack/jobs/{bucket_name}/{repo_address.path()}"
    _create_log_group_if_not_exists(logs_client, bucket_name, log_group_name)


def _create_log_group_if_not_exists(
    logs_client: BaseClient, bucket_name: str, log_group_name: str
):
    response = logs_client.describe_log_groups(logGroupNamePrefix=log_group_name)
    if not response["logGroups"] or not any(
        filter(lambda g: g["logGroupName"] == log_group_name, response["logGroups"])
    ):
        logs_client.create_log_group(
            logGroupName=log_group_name,
            tags={
                "owner": "dstack",
                "dstack_bucket": bucket_name,
            },
        )


def create_log_stream(logs_client: BaseClient, log_group_name: str, run_name: str):
    logs_client.create_log_stream(logGroupName=log_group_name, logStreamName=run_name)


def _filter_logs_events_kwargs(
    bucket_name: str,
    repo_address: RepoAddress,
    run_name: str,
    start_time: int,
    end_time: Optional[int],
    next_token: Optional[str],
):
    filter_logs_events_kwargs = {
        "logGroupName": f"/dstack/jobs/{bucket_name}/{repo_address.path()}",
        "logStreamNames": [run_name],
        "startTime": start_time,
        "interleaved": True,
    }
    if end_time:
        filter_logs_events_kwargs["endTime"] = end_time
    if next_token:
        filter_logs_events_kwargs["nextToken"] = next_token
    return filter_logs_events_kwargs


def poll_logs(
    storage: Storage,
    compute: Compute,
    logs_client: BaseClient,
    bucket_name: str,
    repo_address: RepoAddress,
    job_heads: List[JobHead],
    start_time: int,
    attached: bool,
) -> Generator[LogEvent, None, None]:
    run_name = job_heads[0].run_name
    filter_logs_events_kwargs = _filter_logs_events_kwargs(
        bucket_name, repo_address, run_name, start_time, end_time=None, next_token=None
    )
    jobs_cache = {}
    try:
        if attached:
            for event in _filter_log_events_loop(
                storage,
                compute,
                logs_client,
                repo_address,
                job_heads,
                filter_logs_events_kwargs,
            ):
                yield render_log_message(
                    storage,
                    event,
                    repo_address,
                    jobs_cache,
                )
        else:
            paginator = logs_client.get_paginator("filter_log_events")
            for page in paginator.paginate(**filter_logs_events_kwargs):
                for event in page["events"]:
                    yield render_log_message(
                        storage,
                        event,
                        repo_address,
                        jobs_cache,
                    )
    except Exception as e:
        if (
            hasattr(e, "response")
            and e.response.get("Error")
            and e.response["Error"].get("Code") == "ResourceNotFoundException"
        ):
            return
        else:
            raise e
