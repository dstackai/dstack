import sys
from argparse import Namespace

from rich import print
from rich.prompt import Confirm

from dstack.api.backend import list_backends
from dstack.api.repo import load_repo_data
from dstack.cli.commands import BasicCommand
from dstack.core.error import check_config, check_git


class RMCommand(BasicCommand):
    NAME = "rm"
    DESCRIPTION = "Remove run(s)"

    def __init__(self, parser):
        super(RMCommand, self).__init__(parser)

    def register(self):
        self._parser.add_argument(
            "run_name", metavar="RUN", type=str, nargs="?", help="A name of a run"
        )
        self._parser.add_argument(
            "-a",
            "--all",
            help="Remove all finished runs",
            dest="all",
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
            and (args.yes or Confirm.ask(f"[red]Delete the run '{args.run_name}'?[/]"))
        ) or (args.all and (args.yes or Confirm.ask("[red]Delete all runs?[/]"))):
            repo_data = load_repo_data()
            deleted_run = False
            for backend in list_backends():
                job_heads = backend.list_job_heads(repo_data, args.run_name)
                if job_heads:
                    finished_job_heads = []
                    for job_head in job_heads:
                        if job_head.status.is_finished():
                            finished_job_heads.append(job_head)
                        elif args.run_name:
                            sys.exit("The run is not finished yet. Stop the run first.")
                    for job_head in finished_job_heads:
                        backend.delete_job_head(repo_data, job_head.job_id)
                        deleted_run = True
            if args.run_name and not deleted_run:
                sys.exit(f"Cannot find the run '{args.run_name}'")
            print(f"[grey58]OK[/]")
        else:
            if not args.run_name and not args.all:
                sys.exit("Specify a run name or use --all to delete all runs")
