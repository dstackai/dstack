import sys
from argparse import Namespace

from rich import print
from rich.prompt import Confirm

from dstack.api.backend import list_backends
from dstack.api.repo import load_repo_data
from dstack.cli.commands import BasicCommand
from dstack.core.error import check_config, check_git


def _verb(abort: bool):
    if abort:
        return "Abort"
    else:
        return "Stop"


class StopCommand(BasicCommand):
    NAME = "stop"
    DESCRIPTION = "Stop runs"

    def __init__(self, parser):
        super(StopCommand, self).__init__(parser)

    def register(self):
        self._parser.add_argument(
            "run_name", metavar="RUN", type=str, nargs="?", help="A name of a run"
        )
        self._parser.add_argument(
            "-a",
            "--all",
            help="Stop all unfinished runs",
            dest="all",
            action="store_true",
        )
        self._parser.add_argument(
            "-x",
            "--abort",
            help="Don't wait for a graceful stop and abort the run immediately",
            dest="abort",
            action="store_true",
        )
        self._parser.add_argument(
            "-y", "--yes", help="Don't ask for confirmation", action="store_true"
        )

    @check_config
    @check_git
    def _command(self, args: Namespace):
        if (
            args.run_name
            and (
                args.yes or Confirm.ask(f"[red]{_verb(args.abort)} the run '{args.run_name}'?[/]")
            )
        ) or (args.all and (args.yes or Confirm.ask(f"[red]{_verb(args.abort)} all runs?[/]"))):
            repo_data = load_repo_data()
            for backend in list_backends():
                job_heads = backend.list_job_heads(repo_data, args.run_name)
                if job_heads:
                    for job_head in job_heads:
                        if job_head.status.is_unfinished():
                            backend.stop_job(repo_data, job_head.job_id, args.abort)
                    print(f"[grey58]OK[/]")
                    return
            sys.exit(f"Cannot find the run '{args.run_name}'")
        else:
            if not args.run_name and not args.all:
                sys.exit("Specify a run name or use --all to stop all workflows")
