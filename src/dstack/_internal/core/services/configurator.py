from pathlib import Path
from typing import Optional, Tuple, Union

from dstack._internal.core.errors import ConfigurationError
from dstack._internal.core.models.repos import LocalRepo, RemoteRepo
from dstack._internal.core.models.runs import RunSpec
from dstack._internal.core.services.configs import ConfigManager
from dstack._internal.core.services.configs.configuration import load_configuration
from dstack._internal.core.services.configs.profile import load_profile
from dstack._internal.core.services.repos import load_repo
from dstack._internal.utils.path import PathLike, path_in_dir


def load_run_spec(
    cwd: PathLike,
    working_dir: PathLike,
    configuration_file: Optional[PathLike],
    profile_name: Optional[str],
) -> Tuple[Union[RemoteRepo, LocalRepo], RunSpec]:
    cwd = Path(cwd).absolute()
    repo_config = ConfigManager().get_repo_config(cwd)
    if repo_config is None:
        raise ConfigurationError("Not a dstack repository. Call `dstack init` first")
    repo_dir = Path(repo_config.path).absolute()

    working_dir = (cwd / working_dir).absolute()
    if not path_in_dir(working_dir, repo_dir):
        raise ConfigurationError(
            f"Working directory {working_dir} is not in the repository {repo_dir}"
        )

    configuration, configuration_path = load_configuration(
        repo_dir, working_dir, configuration_file
    )
    profile = load_profile(repo_dir, profile_name)
    repo = load_repo(repo_config)

    return repo, RunSpec(
        run_name="",
        repo_id=repo_config.repo_id,
        repo_data=repo.run_repo_data,
        repo_code_hash=None,  # TODO
        working_dir=str(working_dir.relative_to(repo_dir)),
        configuration_path=configuration_path,
        configuration=configuration,
        profile=profile,
        ssh_key_pub=read_public_ssh_key(repo_config.ssh_key_path),
    )


def read_public_ssh_key(ssh_key_path: PathLike) -> str:
    try:
        with open(str(ssh_key_path) + ".pub", "r") as f:
            return f.read().strip()
    except FileNotFoundError:
        raise ConfigurationError(f"SSH key not found: {ssh_key_path}")
