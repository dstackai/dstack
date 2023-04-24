from argparse import Namespace

from rich.prompt import Confirm

from dstack.api.backend import list_backends
from dstack.api.repos import load_repo
from dstack.cli.commands import BasicCommand
from dstack.cli.common import check_backend, check_config, check_git, check_init, console
from dstack.cli.config import config


def _verb(abort: bool):
    if abort:
        return "Abort"
    else:
        return "Stop"


class StopCommand(BasicCommand):
    NAME = "stop"
    DESCRIPTION = "Stop run(s)"

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
    @check_backend
    @check_init
    def _command(self, args: Namespace):
        if not args.run_name and not args.all:
            console.print("Specify a run name or use --all to stop all workflows")
            exit(1)
        if (
            args.run_name
            and (
                args.yes or Confirm.ask(f"[red]{_verb(args.abort)} the run '{args.run_name}'?[/]")
            )
        ) or (args.all and (args.yes or Confirm.ask(f"[red]{_verb(args.abort)} all runs?[/]"))):
            repo = load_repo(config.repo_user_config)
            found_run = False
            for backend in list_backends(repo):
                job_heads = backend.list_job_heads(args.run_name)
                found_run = len(job_heads) > 0
                for job_head in job_heads:
                    if job_head.status.is_unfinished():
                        backend.stop_job(job_head.job_id, args.abort)
            if args.run_name and not found_run:
                console.print(f"Cannot find the run '{args.run_name}'")
                exit(1)
            console.print(f"[grey58]OK[/]")
