from datetime import datetime
from typing import Generator, Optional

from botocore.client import BaseClient

from dstack._internal.backend.base import jobs as base_jobs
from dstack._internal.backend.base.logs import Logging, fix_log_event_urls, render_log_event
from dstack._internal.backend.base.storage import Storage
from dstack._internal.core.log_event import LogEvent
from dstack._internal.utils.common import (
    datetime_to_timestamp_in_milliseconds,
    timestamps_in_milliseconds_to_datetime,
)


class AWSLogging(Logging):
    def __init__(self, logs_client: BaseClient, bucket_name: str):
        self.logs_client = logs_client
        self.bucket_name = bucket_name

    def poll_logs(
        self,
        storage: Storage,
        repo_id: str,
        run_name: str,
        start_time: datetime,
        end_time: Optional[datetime],
        descending: bool,
        diagnose: bool,
    ) -> Generator[LogEvent, None, None]:
        jobs = base_jobs.list_jobs(storage, repo_id, run_name)
        jobs_map = {j.job_id: j for j in jobs}
        if diagnose:
            runner_id = jobs[0].runner_id
            log_group = f"/dstack/runners/{self.bucket_name}"
            log_stream = runner_id
        else:
            log_group = f"/dstack/jobs/{self.bucket_name}/{repo_id}"
            log_stream = run_name
        filter_logs_events_kwargs = _filter_logs_events_kwargs(
            log_group=log_group,
            log_stream=log_stream,
            start_time=start_time,
            end_time=end_time,
            next_token=None,
        )
        try:
            paginator = self.logs_client.get_paginator("filter_log_events")
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
                    log_event = render_log_event(event)
                    if not diagnose:
                        log_event = fix_log_event_urls(log_event, jobs_map)
                    yield log_event
        except Exception as e:
            if (
                hasattr(e, "response")
                and e.response.get("Error")
                and e.response["Error"].get("Code") == "ResourceNotFoundException"
            ):
                return
            else:
                raise e

    def create_log_groups_if_not_exist(
        self, logs_client: BaseClient, bucket_name: str, repo_id: str
    ):
        _create_log_group_if_not_exists(
            logs_client, bucket_name, f"/dstack/jobs/{bucket_name}/{repo_id}"
        )
        _create_log_group_if_not_exists(logs_client, bucket_name, f"/dstack/runners/{bucket_name}")


def _filter_logs_events_kwargs(
    log_group: str,
    log_stream: str,
    start_time: datetime,
    end_time: Optional[datetime],
    next_token: Optional[str],
):
    filter_logs_events_kwargs = {
        "logGroupName": log_group,
        "logStreamNames": [log_stream],
        "startTime": datetime_to_timestamp_in_milliseconds(start_time),
    }
    if end_time:
        filter_logs_events_kwargs["endTime"] = datetime_to_timestamp_in_milliseconds(end_time)
    if next_token:
        filter_logs_events_kwargs["nextToken"] = next_token
    return filter_logs_events_kwargs


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
