import os
import sys
from argparse import Namespace

from git import InvalidGitRepositoryError
from rich import print

from dstack.backend import load_backend
from dstack.config import ConfigError
from dstack.repo import load_repo_data


def init_func(args: Namespace):
    try:
        local_repo_data = load_repo_data(args.gh_token, args.identity_file)
        local_repo_data.ls_remote()
        backend = load_backend()
        backend.save_repo_credentials(local_repo_data, local_repo_data.repo_credentials())
        print(f"[grey58]OK[/]")
    except InvalidGitRepositoryError:
        sys.exit(f"{os.getcwd()} is not a Git repo")
    except ConfigError:
        sys.exit(f"Call 'dstack config' first")


def register_parsers(main_subparsers):
    parser = main_subparsers.add_parser("init", help="Authorize dstack to access the current Git repo")
    parser.add_argument("-t", "--token", metavar="OAUTH_TOKEN", help="An authentication token for Git", type=str,
                        dest="gh_token")
    parser.add_argument("-i", "--identity", metavar="SSH_PRIVATE_KEY", help="A path to the private SSH key file",
                        type=str, dest="identity_file")
    parser.set_defaults(func=init_func)
