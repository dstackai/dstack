import os
import sys
from argparse import Namespace

from git import InvalidGitRepositoryError
from rich.console import Console
from rich.table import Table

from dstack.backend import load_backend
from dstack.config import ConfigError
from dstack.repo import load_repo_data


def _run_name(repo_data, backend, args):
    if args.run_name_or_tag_name.startswith(":"):
        tag_name = args.run_name_or_tag_name[1:]
        tag_head = backend.get_tag_head(repo_data.repo_user_name, repo_data.repo_name, tag_name)
        if tag_head:
            return tag_head.run_name
        else:
            sys.exit(f"Cannot find the tag '{tag_name}'")
    else:
        run_name = args.run_name_or_tag_name
        job_heads = backend.list_job_heads(repo_data.repo_user_name, repo_data.repo_name, run_name)
        if job_heads:
            return run_name
        else:
            sys.exit(f"Cannot find the run '{run_name}'")


def download_func(args: Namespace):
    try:
        backend = load_backend()
        repo_data = load_repo_data()
        run_name = _run_name(repo_data, backend, args)
        backend.download_run_artifact_files(repo_data.repo_user_name, repo_data.repo_name, run_name, args.output)
    except InvalidGitRepositoryError:
        sys.exit(f"{os.getcwd()} is not a Git repo")
    except ConfigError:
        sys.exit(f"Call 'dstack config' first")


def sizeof_fmt(num, suffix='B'):
    for unit in ['', 'Ki', 'Mi', 'Gi', 'Ti', 'Pi', 'Ei', 'Zi']:
        if abs(num) < 1024.0:
            return "%3.1f%s%s" % (num, unit, suffix)
        num /= 1024.0
    return "%.1f%s%s" % (num, 'Yi', suffix)


def list_func(args: Namespace):
    try:
        backend = load_backend()
        repo_data = load_repo_data()
        run_name = _run_name(repo_data, backend, args)
        run_artifact_files = backend.list_run_artifact_files(repo_data.repo_user_name, repo_data.repo_name, run_name)
        console = Console()
        table = Table(box=None)
        table.add_column("ARTIFACT", style="bold", no_wrap=True)
        table.add_column("FILE")
        table.add_column("SIZE", style="dark_sea_green4")
        previous_artifact_name = None
        for (artifact_name, file_name, file_size) in run_artifact_files:
            table.add_row(artifact_name if previous_artifact_name != artifact_name else "",
                          file_name, sizeof_fmt(file_size))
            previous_artifact_name = artifact_name
        console.print(table)
    except InvalidGitRepositoryError:
        sys.exit(f"{os.getcwd()} is not a Git repo")
    except ConfigError:
        sys.exit(f"Call 'dstack config' first")


def register_parsers(main_subparsers):
    parser = main_subparsers.add_parser("artifacts", help="List or download artifacts")
    subparsers = parser.add_subparsers()

    list_parser = subparsers.add_parser("list", help="List artifacts", )
    list_parser.add_argument("run_name_or_tag_name", metavar="RUN | :TAG", type=str, help="A name of a run or a tag")
    list_parser.set_defaults(func=list_func)

    download_parser = subparsers.add_parser("download", help="Download artifacts", )
    download_parser.add_argument("run_name_or_tag_name", metavar="(RUN | :TAG)", type=str,
                                 help="A name of a run or a tag")
    download_parser.add_argument("-o", "--output", help="The directory to download artifacts to. "
                                                        "By default, it's the current directory.", type=str)
    download_parser.set_defaults(func=download_func)
