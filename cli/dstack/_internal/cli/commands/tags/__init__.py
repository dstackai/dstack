from argparse import Namespace

from rich import print
from rich.prompt import Confirm
from rich.table import Table
from rich_argparse import RichHelpFormatter

from dstack._internal.cli.commands import BasicCommand
from dstack._internal.cli.common import add_project_argument, check_init, console
from dstack._internal.cli.config import get_hub_client
from dstack._internal.core.error import BackendError
from dstack._internal.utils.common import pretty_date


class TAGCommand(BasicCommand):
    NAME = "tags"
    DESCRIPTION = "Manage tags"

    def __init__(self, parser):
        super(TAGCommand, self).__init__(parser)

    def register(self):
        add_project_argument(self._parser)
        subparsers = self._parser.add_subparsers()
        list_parser = subparsers.add_parser(
            "list", help="List tags", formatter_class=RichHelpFormatter
        )
        add_project_argument(list_parser)

        add_tags_parser = subparsers.add_parser(
            "add", help="Add a tag", formatter_class=RichHelpFormatter
        )
        add_project_argument(add_tags_parser)
        add_tags_parser.add_argument(
            "tag_name", metavar="TAG", type=str, help="The name of the tag"
        )
        add_tags_parser.add_argument(
            "run_name", metavar="RUN", type=str, help="The name of the run", nargs="?"
        )
        add_tags_parser.add_argument(
            "-a",
            "--artifact",
            metavar="PATH",
            type=str,
            help="A path to local directory to upload as an artifact",
            action="append",
            dest="artifact_paths",
        )
        add_tags_parser.add_argument(
            "-y", "--yes", help="Don't ask for confirmation", action="store_true"
        )
        add_tags_parser.set_defaults(func=self.add_tag)

        delete_tags_parser = subparsers.add_parser(
            "delete", help="Delete a tag", formatter_class=RichHelpFormatter
        )
        add_project_argument(delete_tags_parser)
        delete_tags_parser.add_argument(
            "tag_name", metavar="TAG_NAME", type=str, help="The name of the tag"
        )
        delete_tags_parser.add_argument(
            "-y", "--yes", help="Don't ask for confirmation", action="store_true"
        )
        delete_tags_parser.set_defaults(func=self.delete_tag)

    @check_init
    def _command(self, args: Namespace):
        table = Table(box=None)
        table.add_column("TAG", style="bold", no_wrap=True)
        table.add_column("CREATED", style="grey58", no_wrap=True)
        table.add_column("RUN", style="grey58", no_wrap=True)
        table.add_column("OWNER", style="grey58", no_wrap=True, max_width=16)
        table.add_column("BACKENDS", style="bold green", no_wrap=True)

        hub_client = get_hub_client(project_name=args.project)
        tag_heads = hub_client.list_tag_heads()
        for tag_head in tag_heads:
            created_at = pretty_date(round(tag_head.created_at / 1000))
            table.add_row(
                tag_head.tag_name,
                created_at,
                tag_head.run_name,
                tag_head.hub_user_name,
            )
        console.print(table)

    @check_init
    def add_tag(self, args: Namespace):
        if not args.run_name and not args.artifact_paths:
            console.print("Specify -r RUN or -a PATH to create a tag")
            exit(1)
        hub_client = get_hub_client(project_name=args.project)
        tag_head = hub_client.get_tag_head(args.tag_name)
        if tag_head is not None:
            if not args.yes and not Confirm.ask(
                f"[red]The tag '{args.tag_name}' already exists. "
                f"Do you want to override it?[/]"
            ):
                return
            hub_client.delete_tag_head(tag_head)
        if args.run_name is not None:
            jobs_heads = hub_client.list_job_heads(args.run_name)
            if len(jobs_heads) == 0:
                console.print(f"The run '{args.run_name}' doesn't exist")
                exit(1)
            try:
                hub_client.add_tag_from_run(args.tag_name, args.run_name, run_jobs=None)
            except BackendError as e:
                print(e)
                exit(1)
        else:
            try:
                hub_client.add_tag_from_local_dirs(args.tag_name, args.artifact_paths)
            except BackendError as e:
                print(e)
                exit(1)
        print(f"[grey58]OK[/]")

    @check_init
    def delete_tag(self, args: Namespace):
        hub_client = get_hub_client(project_name=args.project)
        tag_head = hub_client.get_tag_head(args.tag_name)
        if tag_head is None:
            console.print(f"The tag '{args.tag_name}' doesn't exist")
            exit(1)

        if args.yes or Confirm.ask(f" [red]Delete the tag '{args.tag_name}'?[/]"):
            hub_client.delete_tag_head(tag_head)
            print(f"[grey58]OK[/]")
