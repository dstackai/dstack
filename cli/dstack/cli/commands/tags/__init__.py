import sys
from argparse import Namespace
from rich import print
from rich.console import Console
from rich.prompt import Confirm
from rich.table import Table

from dstack.cli.commands import BasicCommand
from dstack.core.error import check_config, check_git
from dstack.api.repo import load_repo_data
from dstack.util import pretty_date
from dstack.api.backend import list_backends


class TAGCommand(BasicCommand):
    NAME = "tags"
    DESCRIPTION = "Manage tags"

    def __init__(self, parser):
        super(TAGCommand, self).__init__(parser)

    def register(self):
        subparsers = self._parser.add_subparsers()

        add_tags_parser = subparsers.add_parser("add", help="Add a tag")
        add_tags_parser.add_argument(
            "tag_name", metavar="TAG", type=str, help="The name of the tag"
        )
        add_tags_parser.add_argument(
            "run_name", metavar="RUN", type=str, help="A name of a run", nargs="?"
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

        delete_tags_parser = subparsers.add_parser("delete", help="Delete a tag")
        delete_tags_parser.add_argument(
            "tag_name", metavar="TAG_NAME", type=str, help="The name of the tag"
        )
        delete_tags_parser.add_argument(
            "-y", "--yes", help="Don't ask for confirmation", action="store_true"
        )
        delete_tags_parser.set_defaults(func=self.delete_tag)

    @check_config
    @check_git
    def _command(self, args: Namespace):
        repo_data = load_repo_data()
        console = Console()
        table = Table(box=None)
        table.add_column("TAG", style="bold", no_wrap=True)
        table.add_column("CREATED", style="grey58", no_wrap=True)
        table.add_column("RUN", style="grey58", no_wrap=True)
        table.add_column("OWNER", style="grey58", no_wrap=True, max_width=16)
        table.add_column("BACKEND", style="bold green", no_wrap=True, max_width=8)
        for backend in list_backends():
            tag_heads = backend.list_tag_heads(repo_data)
            for tag_head in tag_heads:
                created_at = pretty_date(round(tag_head.created_at / 1000))
                table.add_row(
                    tag_head.tag_name,
                    created_at,
                    tag_head.run_name,
                    tag_head.local_repo_user_name or "",
                    backend.name,
                )
        console.print(table)

    @check_config
    def add_tag(self, args: Namespace):
        if args.run_name or args.artifact_paths:
            repo_data = load_repo_data()
            current_backend = None
            for backend in list_backends():
                tag_head = backend.get_tag_head(repo_data, args.tag_name)
                if tag_head:
                    if args.yes or Confirm.ask(
                        f"[red]The tag '{args.tag_name}' already exists. "
                        f"Do you want to override it?[/]"
                    ):
                        backend.delete_tag_head(repo_data, tag_head)
                        break
                    else:
                        return
                if not (args.run_name is None):
                    jobs_heads = backend.list_job_heads(repo_data, args.run_name)
                    if len(jobs_heads) != 0:
                        backend.add_tag_from_run(
                            repo_data, args.tag_name, args.run_name, run_jobs=None
                        )
                else:
                    backend.add_tag_from_local_dirs(
                        repo_data, args.tag_name, args.artifact_paths
                    )
            print(f"[grey58]OK[/]")
        else:
            sys.exit("Specify -r RUN or -a PATH to create a tag")

    @check_config
    def delete_tag(self, args: Namespace):
        repo_data = load_repo_data()
        current_backend = None
        tag_head = None
        for backend in list_backends():
            tag_head = backend.get_tag_head(repo_data, args.tag_name)
            if tag_head:
                current_backend = backend
                break
        if current_backend is None:
            sys.exit(f"The tag '{args.tag_name}' doesn't exist")
        if args.yes or Confirm.ask(f" [red]Delete the tag '{tag_head.tag_name}'?[/]"):
            current_backend.delete_tag_head(repo_data, tag_head)
            print(f"[grey58]OK[/]")
