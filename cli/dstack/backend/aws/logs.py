from datetime import datetime
from typing import Generator, Optional

from botocore.client import BaseClient

from dstack.backend.base.logs import render_log_message
from dstack.backend.base.storage import Storage
from dstack.core.log_event import LogEvent
from dstack.utils.common import (
    datetime_to_timestamp_in_milliseconds,
    timestamps_in_milliseconds_to_datetime,
)


def poll_logs(
    storage: Storage,
    logs_client: BaseClient,
    bucket_name: str,
    repo_id: str,
    run_name: str,
    start_time: datetime,
    end_time: Optional[datetime],
    descending: bool,
) -> Generator[LogEvent, None, None]:
    jobs_cache = {}
    filter_logs_events_kwargs = _filter_logs_events_kwargs(
        bucket_name, repo_id, run_name, start_time, end_time=end_time, next_token=None
    )
    try:
        paginator = logs_client.get_paginator("filter_log_events")
        pages = paginator.paginate(**filter_logs_events_kwargs)
        # aws sdk doesn't provide a way to order events by descending so we have to do it by hand
        if descending:
            pages = reversed(list(pages))
        for page in pages:
            events = page["events"]
            if descending:
                events = reversed(page["events"])
            for event in events:
                event["timestamp"] = timestamps_in_milliseconds_to_datetime(event["timestamp"])
                yield render_log_message(
                    storage,
                    event,
                    repo_id,
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


def _filter_logs_events_kwargs(
    bucket_name: str,
    repo_id: str,
    run_name: str,
    start_time: datetime,
    end_time: Optional[datetime],
    next_token: Optional[str],
):
    filter_logs_events_kwargs = {
        "logGroupName": f"/dstack/jobs/{bucket_name}/{repo_id}",
        "logStreamNames": [run_name],
        "startTime": datetime_to_timestamp_in_milliseconds(start_time),
    }
    if end_time:
        filter_logs_events_kwargs["endTime"] = datetime_to_timestamp_in_milliseconds(end_time)
    if next_token:
        filter_logs_events_kwargs["nextToken"] = next_token
    return filter_logs_events_kwargs


def create_log_groups_if_not_exist(logs_client: BaseClient, bucket_name: str, repo_id: str):
    _create_log_group_if_not_exists(
        logs_client, bucket_name, f"/dstack/jobs/{bucket_name}/{repo_id}"
    )
    _create_log_group_if_not_exists(logs_client, bucket_name, f"/dstack/runners/{bucket_name}")


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
