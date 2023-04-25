import os
import sys
from argparse import Namespace

from dstack.api.hub import HubClient
from dstack.cli.commands import BasicCommand
from dstack.cli.common import check_backend, check_config, check_git, check_init, console
from dstack.cli.config import config
from dstack.core.repo import RemoteRepo
from dstack.utils.common import since


class LogCommand(BasicCommand):
    NAME = "logs"
    DESCRIPTION = "Show logs"

    def __init__(self, parser):
        super(LogCommand, self).__init__(parser)

    def register(self):
        # TODO: Add --format (short|detailed)
        self._parser.add_argument("run_name", metavar="RUN", type=str, help="A name of a run")
        self._parser.add_argument(
            "-a",
            "--attach",
            help="Whether to continuously poll for new logs. By default, the command "
            "will exit once there are no more logs to display. To exit from this "
            "mode, use Control-C.",
            action="store_true",
        )
        self._parser.add_argument(
            "-s",
            "--since",
            help="From what time to begin displaying logs. By default, logs will be displayed starting "
            "from 24 hours in the past. The value provided can be an ISO 8601 timestamp or a "
            "relative time. For example, a value of 5m would indicate to display logs starting five "
            "minutes in the past.",
            type=str,
            default="1d",
        )

    @check_config
    @check_git
    @check_backend
    @check_init
    def _command(self, args: Namespace):
        start_time = since(args.since)
        repo = RemoteRepo(repo_ref=config.repo_user_config.repo_ref, local_repo_dir=os.getcwd())
        hub_client = HubClient(repo=repo)
        job_heads = hub_client.list_job_heads(args.run_name)
        if len(job_heads) == 0:
            console.print(f"Cannot find the run '{args.run_name}'")
            exit(1)
        try:
            for event in hub_client.poll_logs(run_name=args.run_name, start_time=start_time):
                sys.stdout.write(event.log_message)
        except KeyboardInterrupt:
            pass
