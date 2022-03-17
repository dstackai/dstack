import json
import os
import re
import sys
import time
from argparse import Namespace
from collections import defaultdict
from datetime import datetime, timedelta

from botocore.exceptions import ClientError, ParamValidationError
from botocore.utils import parse_timestamp, datetime2timestamp
from git import InvalidGitRepositoryError

from dstack.cli.common import get_job, get_user_info, boto3_client
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

        filter_logs_events_kwargs = {"interleaved": True, "startTime": to_epoch_millis(args.since)}
        job = get_job(args.run_name_or_job_id, profile)
        if job is not None:
            filter_logs_events_kwargs["logGroupName"] = f"{user_info['user_name']}/{job['run_name']}"
            filter_logs_events_kwargs["logStreamNames"] = [job['job_id']]
        else:
            filter_logs_events_kwargs["logGroupName"] = f"{user_info['user_name']}/{args.run_name_or_job_id}"

        client = boto3_client(user_info, "logs")

        if args.follow is True:
            try:
                for event in _do_filter_log_events(client, filter_logs_events_kwargs):
                    print(json.loads(event["message"].strip())["log"])
            except KeyboardInterrupt:
                # The only way to exit from the --follow is to Ctrl-C. So
                # we should exit the iterator rather than having the
                # KeyboardInterrupt propagate to the rest of the command.
                return

        else:
            paginator = client.get_paginator('filter_log_events')
            for page in paginator.paginate(**filter_logs_events_kwargs):
                for event in page['events']:
                    print(json.loads(event["message"].strip())["log"])

    except InvalidGitRepositoryError:
        sys.exit(f"{os.getcwd()} is not a Git repo")
    except ConfigurationError:
        sys.exit(f"Call 'dstack config' first")


def register_parsers(main_subparsers):
    parser = main_subparsers.add_parser("logs", help="Show logs of a run or job")

    # TODO: Make run_name_or_job_id optional
    # TODO: Add --format (short|detailed)
    parser.add_argument("run_name_or_job_id", metavar="(RUN | JOB)", type=str)
    parser.add_argument("--follow", "-f", help="Whether to continuously poll for new logs. By default, the command "
                                               "will exit once there are no more logs to display. To exit from this "
                                               "mode, use Control-C.", action="store_true")
    parser.add_argument("--since", "-s",
                        help="From what time to begin displaying logs. By default, logs will be displayed starting "
                             "from ten minutes in the past. The value provided can be an ISO 8601 timestamp or a "
                             "relative time. For example, a value of 5m would indicate to display logs starting five "
                             "minutes in the past.", type=str, nargs="?", default="1d")

    parser.set_defaults(func=logs_func)
