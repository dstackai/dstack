import sys
from argparse import Namespace

from dstack.cli.commands import BasicCommand
from dstack.cli.common import add_project_argument, check_init, console
from dstack.cli.config import get_hub_client
from dstack.utils.common import since


class LogCommand(BasicCommand):
    NAME = "logs"
    DESCRIPTION = "Show logs"

    def __init__(self, parser):
        super(LogCommand, self).__init__(parser)

    def register(self):
        # TODO: Add --format (short|detailed)
        add_project_argument(self._parser)
        self._parser.add_argument("run_name", metavar="RUN", type=str, help="The name of the run")
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

    @check_init
    def _command(self, args: Namespace):
        hub_client = get_hub_client(project_name=args.project)
        job_heads = hub_client.list_job_heads(args.run_name)
        if len(job_heads) == 0:
            console.print(f"Cannot find the run '{args.run_name}'")
            exit(1)
        start_time = since(args.since)
        try:
            for event in hub_client.poll_logs(run_name=args.run_name, start_time=start_time):
                sys.stdout.write(event.log_message)
        except KeyboardInterrupt:
            pass
