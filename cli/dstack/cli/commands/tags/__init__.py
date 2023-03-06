import sys
from argparse import Namespace

from rich import print
from rich.console import Console
from rich.prompt import Confirm
from rich.table import Table
from rich_argparse import RichHelpFormatter

from dstack.api.backend import list_backends
from dstack.api.repo import load_repo_data
from dstack.api.tags import list_tag_heads_with_merged_backends
from dstack.backend.base import BackendType
from dstack.cli.commands import BasicCommand
from dstack.core.error import BackendError, check_config, check_git
from dstack.utils.common import pretty_date


class TAGCommand(BasicCommand):
    NAME = "tags"
    DESCRIPTION = "Manage tags"

    def __init__(self, parser):
        super(TAGCommand, self).__init__(parser)

    def register(self):
        subparsers = self._parser.add_subparsers()

        add_tags_parser = subparsers.add_parser(
            "add", help="Add a tag", formatter_class=RichHelpFormatter
        )
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
            "-r", "--remote", help="Upload artifact to remote", action="store_true"
        )
        add_tags_parser.add_argument(
            "-y", "--yes", help="Don't ask for confirmation", action="store_true"
        )
        add_tags_parser.set_defaults(func=self.add_tag)

        delete_tags_parser = subparsers.add_parser(
            "delete", help="Delete a tag", formatter_class=RichHelpFormatter
        )
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
        table.add_column("BACKENDS", style="bold green", no_wrap=True)

        tag_heads = list_tag_heads_with_merged_backends(list_backends(), repo_data)

        for tag_head, backends in tag_heads:
            created_at = pretty_date(round(tag_head.created_at / 1000))
            table.add_row(
                tag_head.tag_name,
                created_at,
                tag_head.run_name,
                tag_head.local_repo_user_name or "",
                ", ".join(b.name for b in backends),
            )
        console.print(table)

    @check_config
    def add_tag(self, args: Namespace):
        if args.run_name or args.artifact_paths:
            repo_data = load_repo_data()
            added_tag = False
            confirmed_override = False
            for backend in list_backends():
                tag_head = backend.get_tag_head(repo_data, args.tag_name)
                if tag_head:
                    if not args.yes and not confirmed_override:
                        confirmed_override = Confirm.ask(
                            f"[red]The tag '{args.tag_name}' already exists. "
                            f"Do you want to override it?[/]"
                        )
                        if not confirmed_override:
                            return
                    backend.delete_tag_head(repo_data, tag_head)
                if args.run_name is not None:
                    jobs_heads = backend.list_job_heads(repo_data, args.run_name)
                    if len(jobs_heads) == 0:
                        continue
                    try:
                        backend.add_tag_from_run(
                            repo_data, args.tag_name, args.run_name, run_jobs=None
                        )
                        added_tag = True
                    except BackendError as e:
                        print(e)
                        exit(1)
                else:
                    if not args.remote and backend.type is BackendType.REMOTE:
                        continue
                    if args.remote and backend.type is BackendType.LOCAL:
                        continue
                    try:
                        backend.add_tag_from_local_dirs(
                            repo_data, args.tag_name, args.artifact_paths
                        )
                    except BackendError as e:
                        print(e)
                        exit(1)
            if args.run_name is not None and not added_tag:
                print(f"The run '{args.run_name}' doesn't exist")
                exit(1)
            print(f"[grey58]OK[/]")
        else:
            sys.exit("Specify -r RUN or -a PATH to create a tag")

    @check_config
    def delete_tag(self, args: Namespace):
        repo_data = load_repo_data()
        tag_heads = []
        for backend in list_backends():
            tag_head = backend.get_tag_head(repo_data, args.tag_name)
            if tag_head is not None:
                tag_heads.append((backend, tag_head))

        if len(tag_heads) == 0:
            sys.exit(f"The tag '{args.tag_name}' doesn't exist")

        if args.yes or Confirm.ask(f" [red]Delete the tag '{args.tag_name}'?[/]"):
            for backend, tag_head in tag_heads:
                backend.delete_tag_head(repo_data, tag_head)
            print(f"[grey58]OK[/]")
