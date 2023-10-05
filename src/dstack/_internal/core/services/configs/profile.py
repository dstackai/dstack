from pathlib import Path
from typing import Optional

import yaml

from dstack._internal.core.errors import ConfigurationError
from dstack._internal.core.models.profiles import Profile, ProfilesConfig
from dstack._internal.utils.path import PathLike


def load_profile(repo_dir: PathLike, profile_name: Optional[str]) -> Profile:
    repo_dir = Path(repo_dir)
    profiles_path = repo_dir / ".dstack/profiles.yml"
    if not profiles_path.exists():
        profiles_path = profiles_path.with_suffix(".yaml")

    config = ProfilesConfig(profiles=[])
    try:
        with profiles_path.open("r") as f:
            config = ProfilesConfig.parse_obj(yaml.safe_load(f))
    except FileNotFoundError:
        pass

    if profile_name is None:
        return config.default()
    try:
        return config.get(profile_name)
    except KeyError:
        raise ConfigurationError(f"No such profile: {profile_name}")
