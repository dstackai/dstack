import os
from contextlib import suppress
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Optional

import git.cmd
import yaml
from git.exc import GitCommandError

from dstack._internal.core.errors import DstackError
from dstack._internal.core.models.repos import RemoteRepoCreds
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
        creds, default_branch = _get_repo_creds_and_default_branch_https(url)
        logger.debug(
            "Git repo %s is public. Using no auth. Default branch: %s", repo_url, default_branch
        )
        return creds, default_branch

    # ssh key provided by the user or pulled from the server
    if identity_file is not None or private_key is not None:
        if identity_file is not None:
            private_key = _read_private_key(identity_file)
            creds, default_branch = _get_repo_creds_and_default_branch_ssh(
                url, identity_file, private_key
            )
            logger.debug(
                "Git repo %s is private. Using identity file: %s. Default branch: %s",
                repo_url,
                identity_file,
                default_branch,
            )
            return creds, default_branch
        elif private_key is not None:
            with NamedTemporaryFile("w+", 0o600) as f:
                f.write(private_key)
                f.flush()
                creds, default_branch = _get_repo_creds_and_default_branch_ssh(
                    url, f.name, private_key
                )
                masked_key = "***" + private_key[-10:] if len(private_key) > 10 else "***MASKED***"
                logger.debug(
                    "Git repo %s is private. Using private key: %s. Default branch: %s",
                    repo_url,
                    masked_key,
                    default_branch,
                )
                return creds, default_branch
        else:
            assert False, "should not reach here"

    # oauth token provided by the user or pulled from the server
    if oauth_token is not None:
        creds, default_branch = _get_repo_creds_and_default_branch_https(url, oauth_token)
        masked_token = (
            len(oauth_token[:-4]) * "*" + oauth_token[-4:]
            if len(oauth_token) > 4
            else "***MASKED***"
        )
        logger.debug(
            "Git repo %s is private. Using provided OAuth token: %s. Default branch: %s",
            repo_url,
            masked_token,
            default_branch,
        )
        return creds, default_branch

    # key from ssh config
    identities = get_host_config(url.original_host).get("identityfile")
    if identities:
        _identity_file = identities[0]
        with suppress(InvalidRepoCredentialsError):
            _private_key = _read_private_key(_identity_file)
            creds, default_branch = _get_repo_creds_and_default_branch_ssh(
                url, _identity_file, _private_key
            )
            logger.debug(
                "Git repo %s is private. Using SSH config identity file: %s. Default branch: %s",
                repo_url,
                _identity_file,
                default_branch,
            )
            return creds, default_branch

    # token from gh config
    if os.path.exists(gh_config_path):
        with open(gh_config_path, "r") as f:
            gh_hosts = yaml.load(f, Loader=yaml.FullLoader)
        _oauth_token = gh_hosts.get(url.host, {}).get("oauth_token")
        if _oauth_token is not None:
            with suppress(InvalidRepoCredentialsError):
                creds, default_branch = _get_repo_creds_and_default_branch_https(url, _oauth_token)
                masked_token = (
                    len(_oauth_token[:-4]) * "*" + _oauth_token[-4:]
                    if len(_oauth_token) > 4
                    else "***MASKED***"
                )
                logger.debug(
                    "Git repo %s is private. Using GitHub config token: %s from %s. Default branch: %s",
                    repo_url,
                    masked_token,
                    gh_config_path,
                    default_branch,
                )
                return creds, default_branch

    # default user key
    if os.path.exists(default_ssh_key):
        with suppress(InvalidRepoCredentialsError):
            _private_key = _read_private_key(default_ssh_key)
            creds, default_branch = _get_repo_creds_and_default_branch_ssh(
                url, default_ssh_key, _private_key
            )
            logger.debug(
                "Git repo %s is private. Using default identity file: %s. Default branch: %s",
                repo_url,
                default_ssh_key,
                default_branch,
            )
            return creds, default_branch

    raise InvalidRepoCredentialsError(
        "No valid default Git credentials found. Pass valid `--token` or `--git-identity`."
    )


def _get_repo_creds_and_default_branch_ssh(
    url: GitRepoURL, identity_file: PathLike, private_key: str
) -> tuple[RemoteRepoCreds, Optional[str]]:
    _url = url.as_ssh()
    env = _make_git_env_for_creds_check(identity_file=identity_file)
    try:
        default_branch = _get_repo_default_branch(_url, env)
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
    env = _make_git_env_for_creds_check()
    try:
        default_branch = _get_repo_default_branch(url.as_https(oauth_token), env)
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


def _make_git_env_for_creds_check(identity_file: Optional[PathLike] = None) -> dict[str, str]:
    # Our goal is to check if _provided_ creds (if any) are correct, so we need to be sure that
    # only the provided creds are used, without falling back to any additional mechanisms.
    # To do this, we:
    # 1. Disable all configs to ignore any stored creds
    # 2. Disable askpass to avoid asking for creds interactively or fetching stored creds from
    # a non-interactive askpass helper (for example, VS Code sets GIT_ASKPASS to its own helper,
    # which silently provides creds to Git).
    return make_git_env(disable_config=True, disable_askpass=True, identity_file=identity_file)


def _get_repo_default_branch(url: str, env: dict[str, str]) -> Optional[str]:
    # Git shipped by Apple with XCode is patched to support an additional config scope
    # above "system" called "xcode". There is no option in `git config list` to show this config,
    # but you can list the merged config (`git config list` without options) and then exclude
    # all settings listed in `git config list --{system,global,local,worktree}`.
    # As of time of writing, there are only two settings in the "xcode" config, one of which breaks
    # our "is repo public?" check, namely "credential.helper=osxkeychain".
    # As there is no way to disable "xcode" config (no env variable, no CLI option, etc.),
    # the only way to disable credential helper is to override this specific setting with an empty
    # string via command line argument: `git -c credential.helper= COMMAND [ARGS ...]`.
    # See: https://github.com/git/git/commit/3d4355712b9fe77a96ad4ad877d92dc7ff6e0874
    # See: https://gist.github.com/ChrisTollefson/ab9c0a5d1dd4dd615217345c6936a307
    _git = git.cmd.Git()(c="credential.helper=")
    # output example: "ref: refs/heads/dev\tHEAD\n545344f77c0df78367085952a97fc3a058eb4c65\tHEAD"
    output: str = _git.ls_remote("--symref", url, "HEAD", env=env)
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
