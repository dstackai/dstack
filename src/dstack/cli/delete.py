import os
import sys
from argparse import Namespace

from git import InvalidGitRepositoryError
from rich import print
from rich.prompt import Confirm

from dstack.backend import load_backend
from dstack.config import ConfigError
from dstack.repo import load_repo_data


def delete_func(args: Namespace):
    if (args.run_name and (args.yes or Confirm.ask(f"[red]Delete the run '{args.run_name}'?[/]"))) \
            or (args.all and (args.yes or Confirm.ask("[red]Delete all runs?[/]"))):
        try:
            repo_data = load_repo_data()
            backend = load_backend()
            job_heads = backend.list_job_heads(repo_data.repo_user_name, repo_data.repo_name, args.run_name)
            if job_heads:
                finished_job_heads = []
                for job_head in job_heads:
                    if job_head.status.is_finished():
                        finished_job_heads.append(job_head)
                    elif args.run_name:
                        sys.exit("The run is not finished yet. Stop the run first.")
                for job_head in finished_job_heads:
                    backend.delete_job_head(repo_data.repo_user_name, repo_data.repo_name, job_head.job_id)
                print(f"[grey58]OK[/]")
            elif args.run_name:
                sys.exit(f"Cannot find the run '{args.run_name}'")
        except InvalidGitRepositoryError:
            sys.exit(f"{os.getcwd()} is not a Git repo")
        except ConfigError:
            sys.exit(f"Call 'dstack config' first")
    else:
        if not args.run_name and not args.all:
            sys.exit("Specify a run name or use --all to delete all runs")


def register_parsers(main_subparsers):
    parser = main_subparsers.add_parser("delete", help="Delete runs")

    parser.add_argument("run_name", metavar="RUN", type=str, nargs="?", help="A name of a run")
    parser.add_argument("-a", "--all", help="Delete all finished runs", dest="all", action="store_true")
    parser.add_argument("-y", "--yes", help="Don't ask for confirmation", action="store_true")

    parser.set_defaults(func=delete_func)
