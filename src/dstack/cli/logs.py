import json
import os
import re
import sys
import time
import urllib
from argparse import Namespace
from collections import defaultdict
from datetime import datetime, timedelta
from json import JSONDecodeError
from rich import print

from botocore.exceptions import ClientError, ParamValidationError
from botocore.utils import parse_timestamp, datetime2timestamp
from git import InvalidGitRepositoryError

from dstack.cli.common import get_user_info, boto3_client, get_jobs, get_job
from dstack.config import get_config, ConfigurationError

SLEEP_SECONDS = 1


def _get_latest_events_and_timestamp(event_ids_per_timestamp):
    if event_ids_per_timestamp:
        # Keep only ids of the events with the newest timestamp
        newest_timestamp = max(event_ids_per_timestamp.keys())
        event_ids_per_timestamp = defaultdict(
            set, {newest_timestamp: event_ids_per_timestamp[newest_timestamp]}
        )
    return event_ids_per_timestamp


def _reset_filter_log_events_params(fle_kwargs, event_ids_per_timestamp):
    # Remove nextToken and update startTime for the next request
    # with the timestamp of the newest event
    if event_ids_per_timestamp:
        fle_kwargs['startTime'] = max(
            event_ids_per_timestamp.keys()
        )
    fle_kwargs.pop('nextToken', None)


def _do_filter_log_events(client, filter_logs_events_kwargs):
    event_ids_per_timestamp = defaultdict(set)
    while True:
        try:
            response = client.filter_log_events(
                **filter_logs_events_kwargs)
        except (ClientError, ParamValidationError):
            sys.exit("Invalid MFA one time pass code")

        for event in response['events']:
            # For the case where we've hit the last page, we will be
            # reusing the newest timestamp of the received events to keep polling.
            # This means it is possible that duplicate log events with same timestamp
            # are returned back which we do not want to yield again.
            # We only want to yield log events that we have not seen.
            if event['eventId'] not in event_ids_per_timestamp[event['timestamp']]:
                event_ids_per_timestamp[event['timestamp']].add(event['eventId'])
                yield event
        event_ids_per_timestamp = _get_latest_events_and_timestamp(
            event_ids_per_timestamp
        )
        if 'nextToken' in response:
            filter_logs_events_kwargs['nextToken'] = response['nextToken']
        else:
            _reset_filter_log_events_params(
                filter_logs_events_kwargs,
                event_ids_per_timestamp
            )
            time.sleep(SLEEP_SECONDS)


def _relative_timestamp_to_datetime(amount, unit):
    multiplier = {
        's': 1,
        'm': 60,
        'h': 3600,
        'd': 24 * 3600,
        'w': 7 * 24 * 3600,
    }[unit]
    return datetime.utcnow() + timedelta(seconds=amount * multiplier * -1)


def to_epoch_millis(timestamp):
    regex = re.compile(
        r"(?P<amount>\d+)(?P<unit>s|m|h|d|w)$"
    )
    re_match = regex.match(timestamp)
    if re_match:
        datetime_value = _relative_timestamp_to_datetime(
            int(re_match.group('amount')), re_match.group('unit')
        )
    else:
        datetime_value = parse_timestamp(timestamp)
    return int(datetime2timestamp(datetime_value) * 1000)


def logs_func(args: Namespace):
    try:
        dstack_config = get_config()
        # TODO: Support non-default profiles
        profile = dstack_config.get_profile("default")
        user_info = get_user_info(profile)

        filter_logs_events_kwargs = {"interleaved": True, "startTime": to_epoch_millis(args.since),
                                     "logGroupName": f"{user_info['user_name']}/{args.run_name}"}
        job_host_names = {}
        job_ports = {}
        job_apps = {}
        if args.workflow_name is not None:
            jobs = list(filter(lambda j: j["workflow_name"] == args.workflow_name, get_jobs(args.run_name, profile)))
            for job in jobs:
                job_host_names[job["job_id"]] = job["host_name"] or ("none" if job["status"] != "submitted" else None)
                job_apps[job["job_id"]] = job["apps"]
                job_ports[job["job_id"]] = job["ports"]
            if len(jobs) == 0:
                # TODO: Handle not found error
                sys.exit(0)
            filter_logs_events_kwargs["logStreamNames"] = [job['job_id'] for job in jobs]

        client = boto3_client(user_info, "logs")

        if args.follow is True:
            try:
                for event in _do_filter_log_events(client, filter_logs_events_kwargs):
                    print_log_event(event, job_host_names, job_ports, job_apps, profile)
            except KeyboardInterrupt as e:
                # The only way to exit from the --follow is to Ctrl-C. So
                # we should exit the iterator rather than having the
                # KeyboardInterrupt propagate to the rest of the command.
                if hasattr(args, "from_run"):
                    raise e

        else:
            paginator = client.get_paginator('filter_log_events')
            for page in paginator.paginate(**filter_logs_events_kwargs):
                for event in page['events']:
                    try:
                        print_log_event(event, job_host_names, job_ports, job_apps, profile)
                    except JSONDecodeError:
                        pass

    except InvalidGitRepositoryError:
        sys.exit(f"{os.getcwd()} is not a Git repo")
    except ConfigurationError:
        sys.exit(f"Call 'dstack config' first")


def print_log_event(event, job_host_names, job_ports, job_apps, profile):
    job_id = event["logStreamName"]
    if job_id not in job_host_names:
        job = get_job(job_id, profile)
        job_host_names[job_id] = job["host_name"] or "none"
        job_ports[job_id] = job.get("ports")
        job_apps[job_id] = job.get("apps")
    message = json.loads(event["message"].strip())["log"]
    host_name = job_host_names[job_id]
    ports = job_ports[job_id]
    apps = job_apps[job_id]
    pat = re.compile(f'http://(localhost|0.0.0.0|{host_name}):[\\S]*[^(.+)\\s\\n\\r]')
    if re.search(pat, message):
        if host_name != "none" and ports and apps:
            for app in apps:
                port = ports[app["port_index"]]
                url_path = app.get("url_path") or ""
                url_query_params = app.get("url_query_params")
                url_query = ("?" + urllib.parse.urlencode(url_query_params)) if url_query_params else ""
                app_url = f"http://{host_name}:{port}"
                if url_path or url_query_params:
                    app_url += "/"
                    if url_query_params:
                        app_url += url_query
                message = re.sub(pat, app_url, message)
    print(message)


def register_parsers(main_subparsers):
    parser = main_subparsers.add_parser("logs", help="Show logs")

    # TODO: Make run_name_or_job_id optional
    # TODO: Add --format (short|detailed)
    parser.add_argument("run_name", metavar="RUN", type=str, help="A name of a run")
    parser.add_argument("workflow_name", metavar="WORKFLOW", type=str, nargs="?", help="A name of a workflow")
    parser.add_argument("--follow", "-f", help="Whether to continuously poll for new logs. By default, the command "
                                               "will exit once there are no more logs to display. To exit from this "
                                               "mode, use Control-C.", action="store_true")
    parser.add_argument("--since", "-s",
                        help="From what time to begin displaying logs. By default, logs will be displayed starting "
                             "from ten minutes in the past. The value provided can be an ISO 8601 timestamp or a "
                             "relative time. For example, a value of 5m would indicate to display logs starting five "
                             "minutes in the past.", type=str, default="1d")

    parser.set_defaults(func=logs_func)
