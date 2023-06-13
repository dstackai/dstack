from argparse import Namespace

from rich.prompt import Confirm

from dstack._internal.cli.commands import BasicCommand
from dstack._internal.cli.common import add_project_argument, check_init, console
from dstack._internal.cli.config import get_hub_client


class RMCommand(BasicCommand):
    NAME = "rm"
    DESCRIPTION = "Remove run(s)"

    def __init__(self, parser):
        super(RMCommand, self).__init__(parser)

    def register(self):
        add_project_argument(self._parser)
        self._parser.add_argument(
            "run_name", metavar="RUN", type=str, nargs="?", help="The name of the run"
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

    @check_init
    def _command(self, args: Namespace):
        if (
            args.run_name
            and (args.yes or Confirm.ask(f"[red]Delete the run '{args.run_name}'?[/]"))
        ) or (args.all and (args.yes or Confirm.ask("[red]Delete all runs?[/]"))):
            hub_client = get_hub_client(project_name=args.project)
            deleted_run = False
            job_heads = hub_client.list_job_heads(args.run_name)
            if job_heads:
                finished_job_heads = []
                for job_head in job_heads:
                    if job_head.status.is_finished():
                        finished_job_heads.append(job_head)
                    elif args.run_name:
                        console.print("The run is not finished yet. Stop the run first.")
                        exit(1)
                for job_head in finished_job_heads:
                    hub_client.delete_job_head(job_head.job_id)
                    deleted_run = True
            if args.run_name and not deleted_run:
                console.print(f"Cannot find the run '{args.run_name}'")
                exit(1)
            console.print(f"[grey58]OK[/]")
        else:
            if not args.run_name and not args.all:
                console.print("Specify a run name or use --all to delete all runs")
                exit(1)
