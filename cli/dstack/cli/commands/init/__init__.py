from argparse import Namespace

from rich import print

from dstack.api.backend import list_backends
from dstack.api.repo import load_repo_data
from dstack.cli.commands import BasicCommand
from dstack.core.error import check_config, check_git


class InitCommand(BasicCommand):
    NAME = "init"
    DESCRIPTION = "Authorize dstack to access the current Git repo"

    def __init__(self, parser):
        super(InitCommand, self).__init__(parser)

    def register(self):
        self._parser.add_argument(
            "-t",
            "--token",
            metavar="OAUTH_TOKEN",
            help="An authentication token for Git",
            type=str,
            dest="gh_token",
        )
        self._parser.add_argument(
            "-i",
            "--identity",
            metavar="SSH_PRIVATE_KEY",
            help="A path to the private SSH key file",
            type=str,
            dest="identity_file",
        )

    @check_config
    @check_git
    def _command(self, args: Namespace):
        local_repo_data = load_repo_data(args.gh_token, args.identity_file)
        local_repo_data.ls_remote()
        for backend in list_backends():
            backend.save_repo_credentials(local_repo_data, local_repo_data.repo_credentials())
        print(f"[grey58]OK[/]")
