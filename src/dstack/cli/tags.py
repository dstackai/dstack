import sys
from argparse import Namespace

from rich import print
from rich.console import Console
from rich.prompt import Confirm
from rich.table import Table

from dstack.backend import load_backend
from dstack.cli.common import pretty_date
from dstack.config import ConfigError
from dstack.repo import load_repo_data


def list_tags_func(_: Namespace):
    try:
        backend = load_backend()
        repo_data = load_repo_data()
        tag_heads = backend.list_tag_heads(repo_data.repo_user_name, repo_data.repo_name)
        console = Console()
        table = Table(box=None)
        table.add_column("TAG", style="bold", no_wrap=True)
        table.add_column("RUN", style="grey58", no_wrap=True)
        # table.add_column("WORKFLOW", style="grey58", width=12)
        # table.add_column("PROVIDER", style="grey58", width=12)
        table.add_column("ARTIFACTS", style="grey58", width=12)
        table.add_column("CREATED", style="grey58", no_wrap=True)
        for tag_head in tag_heads:
            created_at = pretty_date(round(tag_head.created_at / 1000))
            table.add_row(
                tag_head.tag_name,
                tag_head.run_name,
                # tag_head.workflow_name,
                # tag_head.provider_name,
                '\n'.join([a.artifact_path for a in tag_head.artifact_heads or []]),
                created_at
            )
        console.print(table)
    except ConfigError:
        sys.exit(f"Call 'dstack config' first")


def add_tag_func(args: Namespace):
    if args.run_name or args.artifact_paths:
        try:
            backend = load_backend()
            repo_data = load_repo_data()
            tag_head = backend.get_tag_head(repo_data.repo_user_name, repo_data.repo_name, args.tag_name)
            if tag_head:
                if args.yes or Confirm.ask(f"[red]The tag '{args.tag_name}' already exists. "
                                           f"Do you want to override it?[/]"):
                    backend.delete_tag_head(repo_data.repo_user_name, repo_data.repo_name, tag_head)
                else:
                    return
            if args.run_name:
                backend.add_tag_from_run(repo_data.repo_user_name, repo_data.repo_name, args.tag_name, args.run_name,
                                         run_jobs=None)
            else:
                backend.add_tag_from_local_dirs(repo_data, args.tag_name, args.artifact_paths)
            print(f"[grey58]OK[/]")
        except ConfigError:
            sys.exit(f"Call 'dstack config' first")
    else:
        sys.exit("Specify -r RUN or -a PATH to create a tag")


def delete_tag_func(args: Namespace):
    try:
        backend = load_backend()
        repo_data = load_repo_data()
        tag_head = backend.get_tag_head(repo_data.repo_user_name, repo_data.repo_name, args.tag_name)
        if not tag_head:
            sys.exit(f"The tag '{args.tag_name}' doesn't exist")
        elif Confirm.ask(f" [red]Delete the tag '{tag_head.tag_name}'?[/]"):
            backend.delete_tag_head(repo_data.repo_user_name, repo_data.repo_name, tag_head)
            print(f"[grey58]OK[/]")
    except ConfigError:
        sys.exit(f"Call 'dstack config' first")


def register_parsers(main_subparsers):
    parser = main_subparsers.add_parser("tags", help="Manage tags")
    parser.set_defaults(func=list_tags_func)

    subparsers = parser.add_subparsers()

    subparsers.add_parser("list", help="List tags")

    add_tags_parser = subparsers.add_parser("add", help="Add a tag")
    add_tags_parser.add_argument("tag_name", metavar="TAG", type=str, help="The name of the tag")
    add_tags_parser.add_argument("run_name", metavar="RUN", type=str, help="A name of a run", nargs="?")
    add_tags_parser.add_argument("-a", "--artifact", metavar="PATH", type=str,
                                 help="A path to local directory to upload as an artifact", action="append",
                                 dest="artifact_paths")
    parser.add_argument("-y", "--yes", help="Don't ask for confirmation", action="store_true")
    add_tags_parser.set_defaults(func=add_tag_func)

    delete_tags_parser = subparsers.add_parser("delete", help="Delete a tag")
    delete_tags_parser.add_argument("tag_name", metavar="TAG_NAME", type=str, help="The name of the tag")
    delete_tags_parser.set_defaults(func=delete_tag_func)
