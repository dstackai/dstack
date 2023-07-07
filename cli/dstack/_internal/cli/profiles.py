from pathlib import Path

import yaml

from dstack._internal.core.profile import ProfilesConfig


def load_profiles() -> ProfilesConfig:
    # NOTE: This only supports local profiles
    profiles_path = Path(".dstack") / "profiles.yml"
    if not profiles_path.exists():
        profiles_path = Path(".dstack") / "profiles.yaml"
    if not profiles_path.exists():
        return ProfilesConfig(profiles=[])

    return ProfilesConfig.parse_obj(yaml.safe_load(profiles_path.read_text()))
