import sys
from argparse import Namespace

from dstack._internal.cli.commands import BasicCommand
from dstack._internal.cli.utils.common import add_project_argument, check_init, console
from dstack._internal.cli.utils.config import get_hub_client
from dstack._internal.utils.common import since


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
            "-s",
            "--since",
            help="From what time to begin displaying logs. By default, logs will be displayed starting "
            "from 24 hours in the past. The value provided can be an ISO 8601 timestamp or a "
            "relative time. For example, a value of 5m would indicate to display logs starting five "
            "minutes in the past.",
            type=str,
            default="1d",
        )
        self._parser.add_argument(
            "-d",
            "--diagnose",
            help="Show diagnostic logs",
            action="store_true",
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
            for event in hub_client.poll_logs(
                run_name=args.run_name, start_time=start_time, diagnose=args.diagnose
            ):
                sys.stdout.write(event.log_message)
                if args.diagnose:
                    print()
        except KeyboardInterrupt:
            pass
