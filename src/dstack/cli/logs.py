import os
import re
import sys
from argparse import Namespace
from datetime import datetime, timedelta
from typing import List

from botocore.utils import parse_timestamp, datetime2timestamp
from git import InvalidGitRepositoryError
from rich import print

from dstack.backend import load_backend, Backend
from dstack.jobs import JobHead
from dstack.repo import load_repo_data
from dstack.config import ConfigError


def _relative_timestamp_to_datetime(amount, unit):
    multiplier = {
        's': 1,
        'm': 60,
        'h': 3600,
        'd': 24 * 3600,
        'w': 7 * 24 * 3600,
    }[unit]
    return datetime.utcnow() + timedelta(seconds=amount * multiplier * -1)


def since(timestamp):
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
        backend = load_backend()
        repo_data = load_repo_data()
        start_time = since(args.since)
        job_heads = backend.list_job_heads(repo_data.repo_user_name, repo_data.repo_name, args.run_name)
        if job_heads:
            poll_logs(backend, repo_data.repo_user_name, repo_data.repo_name, job_heads, start_time, args.attach)
        else:
            sys.exit(f"Cannot find the run '{args.run_name}'")
    except InvalidGitRepositoryError:
        sys.exit(f"{os.getcwd()} is not a Git repo")
    except ConfigError:
        sys.exit(f"Call 'dstack config' first")


def poll_logs(backend: Backend, repo_user_name: str, repo_name: str, job_heads: List[JobHead], start_time: int,
              attach: bool, from_run: bool = False):
    try:
        for event in backend.poll_logs(repo_user_name, repo_name, job_heads, start_time, attach):
            print(event.log_message)
    except KeyboardInterrupt as e:
        if attach is True:
            # The only way to exit from the --attach is to Ctrl-C. So
            # we should exit the iterator rather than having the
            # KeyboardInterrupt propagate to the rest of the command.
            if from_run:
                raise e


def register_parsers(main_subparsers):
    parser = main_subparsers.add_parser("logs", help="Show logs")

    # TODO: Add --format (short|detailed)
    parser.add_argument("run_name", metavar="RUN", type=str, help="A name of a run")
    parser.add_argument("-a", "--attach", help="Whether to continuously poll for new logs. By default, the command "
                                               "will exit once there are no more logs to display. To exit from this "
                                               "mode, use Control-C.", action="store_true")
    parser.add_argument("-s", "--since",
                        help="From what time to begin displaying logs. By default, logs will be displayed starting "
                             "from 24 hours in the past. The value provided can be an ISO 8601 timestamp or a "
                             "relative time. For example, a value of 5m would indicate to display logs starting five "
                             "minutes in the past.", type=str, default="1d")

    parser.set_defaults(func=logs_func)
