from pathlib import Path
from typing import Optional, Tuple

import yaml

from dstack._internal.core.errors import ConfigurationError
from dstack._internal.core.models.configurations import AnyRunConfiguration
from dstack._internal.core.models.configurations import (
    parse_run_configuration as parse_configuration,
)
from dstack._internal.core.models.profiles import Profile, ProfilesConfig
from dstack._internal.utils.common import get_dstack_dir
from dstack._internal.utils.path import PathLike, path_in_dir


def load_profile(repo_dir: PathLike, profile_name: Optional[str]) -> Profile:
    """
    Loads a repo profile from `.dstack/profiles.yml` or global profile from `~/.dstack/profiles.yml`.
    If `profile_name` is not specified, the default profile is loaded.
    :param repo_dir: The path to the repository root directory.
    :param profile_name: The name of the profile to load.
    :return: Loaded profile.
    """
    repo_profiles_path = Path(repo_dir) / ".dstack/profiles.yml"
    if not repo_profiles_path.exists():
        repo_profiles_path = repo_profiles_path.with_suffix(".yaml")
    repo_profile = _load_profile_from_path(
        profiles_path=repo_profiles_path,
        profile_name=profile_name,
    )
    if repo_profile is not None:
        return repo_profile

    repo_profiles_path = Path(repo_dir) / ".dstack/profiles.yml"
    if not repo_profiles_path.exists():
        repo_profiles_path = repo_profiles_path.with_suffix(".yaml")

    dstack_dir = get_dstack_dir()
    global_profiles_path = dstack_dir / "profiles.yml"
    if not global_profiles_path.exists():
        global_profiles_path = global_profiles_path.with_suffix(".yaml")

    global_profile = _load_profile_from_path(
        profiles_path=global_profiles_path,
        profile_name=profile_name,
    )
    if global_profile is not None:
        return global_profile

    if profile_name is None:
        return Profile(name="default")

    raise ConfigurationError(f"No such profile: {profile_name}")


def load_configuration(
    repo_dir: PathLike,
    work_dir: Optional[PathLike] = None,
    configuration_file: Optional[PathLike] = None,
) -> Tuple[str, AnyRunConfiguration]:
    """
    Loads a configuration from file. If the file is not specified, loads from `.dstack.yml` if working directory.
    :param repo_dir: The path to the repository root directory.
    :param work_dir: The path to the working directory, relative to the repository root directory.
    :param configuration_file: The path to the configuration file, relative to the repository root directory.
    :return: Path to the configuration file and loaded configuration.
    """
    repo_dir = Path(repo_dir)
    work_dir = repo_dir / (work_dir or ".")
    if not path_in_dir(work_dir, repo_dir):
        raise ConfigurationError("Working directory is outside of the repo")

    if configuration_file is None:
        configuration_path = work_dir / ".dstack.yml"
        if not configuration_path.exists():
            configuration_path = configuration_path.with_suffix(".yaml")
    else:
        configuration_path = repo_dir / configuration_file
        if not path_in_dir(configuration_path, repo_dir):
            raise ConfigurationError("Configuration file is outside of the repo")

    try:
        with open(configuration_path, "r") as f:
            conf = parse_configuration(yaml.safe_load(f))
    except OSError:
        raise ConfigurationError(f"Failed to load configuration from {configuration_path}")
    return str(configuration_path.relative_to(repo_dir)), conf


def _load_profile_from_path(profiles_path: Path, profile_name: Optional[str]) -> Optional[Profile]:
    if not profiles_path.exists():
        profiles_path = profiles_path.with_suffix(".yaml")

    try:
        with profiles_path.open("r") as f:
            config = ProfilesConfig.parse_obj(yaml.safe_load(f))
    except FileNotFoundError:
        return None

    if profile_name is None:
        return config.default()

    try:
        return config.get(profile_name)
    except KeyError:
        return None
