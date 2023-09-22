import argparse
from pathlib import Path
from typing import Optional

import giturlparse
from git import InvalidGitRepositoryError

from dstack._internal.cli.commands import APIBaseCommand
from dstack._internal.core.errors import CLIError
from dstack._internal.core.models.repos import LocalRepo, RemoteRepo
from dstack._internal.core.models.repos.base import RepoType
from dstack._internal.core.services.configs import ConfigManager
from dstack._internal.core.services.repos import (
    InvalidRepoCredentialsError,
    get_local_repo_credentials,
)
from dstack._internal.utils.crypto import generate_rsa_key_pair


class InitCommand(APIBaseCommand):
    NAME = "init"
    DESCRIPTION = "Initialize the repo"

    def _command(self, args: argparse.Namespace):
        super()._command(args)
        repo_path = Path.cwd()
        try:
            if args.local:  # force fallback to LocalRepo
                raise InvalidGitRepositoryError()
            repo = RemoteRepo(local_repo_dir=repo_path)
            try:
                repo_credentials = get_local_repo_credentials(
                    repo_data=repo.run_repo_data,
                    identity_file=args.git_identity_file,
                    oauth_token=args.gh_token,
                    original_hostname=giturlparse.parse(repo.repo_url).resource,
                )
            except InvalidRepoCredentialsError as e:
                raise CLIError(*e.args)
        except InvalidGitRepositoryError:
            repo = LocalRepo(repo_dir=repo_path)
            repo_credentials = None

        config = ConfigManager()
        config.save_repo_config(
            repo_path=repo_path,
            repo_id=repo.repo_id,
            repo_type=RepoType(repo.run_repo_data.repo_type),
            ssh_key_path=get_ssh_keypair(args.ssh_identity_file, config.dstack_key_path),
        )
        self.api_client.repos.init(
            self.project_name, repo.repo_id, repo.run_repo_data, repo_credentials
        )
        print("OK")

    def _register(self):
        super()._register()
        self._parser.add_argument(
            "-t",
            "--token",
            metavar="OAUTH_TOKEN",
            help="An authentication token for Git",
            type=str,
            dest="gh_token",
        )
        self._parser.add_argument(
            "--git-identity",
            metavar="SSH_PRIVATE_KEY",
            help="A path to the private SSH key file for non-public repositories",
            type=str,
            dest="git_identity_file",
        )
        self._parser.add_argument(
            "--ssh-identity",
            metavar="SSH_PRIVATE_KEY",
            help="A path to the private SSH key file for SSH tunneling",
            type=Path,
            dest="ssh_identity_file",
        )
        self._parser.add_argument(
            "--local",
            action="store_true",
            help="Do not use git",
        )


def get_ssh_keypair(key_path: Optional[Path], dstack_key_path: Path) -> str:
    """Returns a path to the private key"""
    if key_path is not None:
        key_path = key_path.expanduser().resolve()
        pub_key = (
            key_path
            if key_path.suffix == ".pub"
            else key_path.with_suffix(key_path.suffix + ".pub")
        )
        private_key = pub_key.with_suffix("")
        if pub_key.exists() and private_key.exists():
            return str(private_key)
        raise CLIError(
            f"Make sure valid keypair exists: {private_key}(.pub) and rerun `dstack init`"
        )

    if not dstack_key_path.exists():
        generate_rsa_key_pair(private_key_path=dstack_key_path)
    return str(dstack_key_path)
