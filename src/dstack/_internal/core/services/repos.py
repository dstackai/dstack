import os
from contextlib import suppress
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Optional, Union

import git.cmd
import yaml
from git.exc import GitCommandError

from dstack._internal.core.errors import DstackError
from dstack._internal.core.models.config import RepoConfig
from dstack._internal.core.models.repos import LocalRepo, RemoteRepo, RemoteRepoCreds
from dstack._internal.core.models.repos.remote import GitRepoURL
from dstack._internal.utils.logging import get_logger
from dstack._internal.utils.path import PathLike
from dstack._internal.utils.ssh import get_host_config, make_git_env, try_ssh_key_passphrase

logger = get_logger(__name__)

gh_config_path = os.path.expanduser("~/.config/gh/hosts.yml")
default_ssh_key = os.path.expanduser("~/.ssh/id_rsa")


class InvalidRepoCredentialsError(DstackError):
    pass


def get_repo_creds_and_default_branch(
    repo_url: str,
    identity_file: Optional[PathLike] = None,
    private_key: Optional[str] = None,
    oauth_token: Optional[str] = None,
) -> tuple[RemoteRepoCreds, Optional[str]]:
    url = GitRepoURL.parse(repo_url, get_ssh_config=get_host_config)

    # no auth
    with suppress(InvalidRepoCredentialsError):
        return _get_repo_creds_and_default_branch_https(url)

    # ssh key provided by the user or pulled from the server
    if identity_file is not None or private_key is not None:
        if identity_file is not None:
            private_key = _read_private_key(identity_file)
            return _get_repo_creds_and_default_branch_ssh(url, identity_file, private_key)
        elif private_key is not None:
            with NamedTemporaryFile("w+", 0o600) as f:
                f.write(private_key)
                f.flush()
                return _get_repo_creds_and_default_branch_ssh(url, f.name, private_key)
        else:
            assert False, "should not reach here"

    # oauth token provided by the user or pulled from the server
    if oauth_token is not None:
        return _get_repo_creds_and_default_branch_https(url, oauth_token)

    # key from ssh config
    identities = get_host_config(url.original_host).get("identityfile")
    if identities:
        _identity_file = identities[0]
        with suppress(InvalidRepoCredentialsError):
            _private_key = _read_private_key(_identity_file)
            return _get_repo_creds_and_default_branch_ssh(url, _identity_file, _private_key)

    # token from gh config
    if os.path.exists(gh_config_path):
        with open(gh_config_path, "r") as f:
            gh_hosts = yaml.load(f, Loader=yaml.FullLoader)
        _oauth_token = gh_hosts.get(url.host, {}).get("oauth_token")
        if _oauth_token is not None:
            with suppress(InvalidRepoCredentialsError):
                return _get_repo_creds_and_default_branch_https(url, _oauth_token)

    # default user key
    if os.path.exists(default_ssh_key):
        with suppress(InvalidRepoCredentialsError):
            _private_key = _read_private_key(default_ssh_key)
            return _get_repo_creds_and_default_branch_ssh(url, default_ssh_key, _private_key)

    raise InvalidRepoCredentialsError(
        "No valid default Git credentials found. Pass valid `--token` or `--git-identity`."
    )


def _get_repo_creds_and_default_branch_ssh(
    url: GitRepoURL, identity_file: PathLike, private_key: str
) -> tuple[RemoteRepoCreds, Optional[str]]:
    _url = url.as_ssh()
    try:
        default_branch = _get_repo_default_branch(_url, make_git_env(identity_file=identity_file))
    except GitCommandError as e:
        message = f"Cannot access `{_url}` using the `{identity_file}` private SSH key"
        raise InvalidRepoCredentialsError(message) from e
    creds = RemoteRepoCreds(
        clone_url=_url,
        private_key=private_key,
        oauth_token=None,
    )
    return creds, default_branch


def _get_repo_creds_and_default_branch_https(
    url: GitRepoURL, oauth_token: Optional[str] = None
) -> tuple[RemoteRepoCreds, Optional[str]]:
    _url = url.as_https()
    try:
        default_branch = _get_repo_default_branch(url.as_https(oauth_token), make_git_env())
    except GitCommandError as e:
        message = f"Cannot access `{_url}`"
        if oauth_token is not None:
            masked_token = len(oauth_token[:-4]) * "*" + oauth_token[-4:]
            message = f"{message} using the `{masked_token}` token"
        raise InvalidRepoCredentialsError(message) from e
    creds = RemoteRepoCreds(
        clone_url=_url,
        private_key=None,
        oauth_token=oauth_token,
    )
    return creds, default_branch


def _get_repo_default_branch(url: str, env: dict[str, str]) -> Optional[str]:
    # output example: "ref: refs/heads/dev\tHEAD\n545344f77c0df78367085952a97fc3a058eb4c65\tHEAD"
    # Disable credential helpers to exclude any default credentials from being used
    output: str = git.cmd.Git()(c="credential.helper=").ls_remote("--symref", url, "HEAD", env=env)
    for line in output.splitlines():
        # line format: `<oid> TAB <ref> LF`
        oid, _, ref = line.partition("\t")
        if oid.startswith("ref:") and ref == "HEAD":
            return oid.rsplit("/", maxsplit=1)[-1]
    return None


def _read_private_key(identity_file: PathLike) -> str:
    identity_file = Path(identity_file).expanduser().resolve()
    if not Path(identity_file).exists():
        raise InvalidRepoCredentialsError(f"The `{identity_file}` private SSH key doesn't exist")
    if not os.access(identity_file, os.R_OK):
        raise InvalidRepoCredentialsError(f"Cannot access the `{identity_file}` private SSH key")
    if not try_ssh_key_passphrase(identity_file):
        raise InvalidRepoCredentialsError(
            f"Cannot use the `{identity_file}` private SSH key. "
            "Ensure that it is valid and passphrase-free"
        )
    with open(identity_file, "r") as file:
        return file.read()


# Used for `config.yml` only, remove it with `repos` in `config.yml`
def load_repo(config: RepoConfig) -> Union[RemoteRepo, LocalRepo]:
    if config.repo_type == "remote":
        return RemoteRepo(repo_id=config.repo_id, local_repo_dir=config.path)
    elif config.repo_type == "local":
        return LocalRepo(repo_id=config.repo_id, repo_dir=config.path)
    raise TypeError(f"Unknown repo_type: {config.repo_type}")
