import json
from pathlib import Path
from typing import Dict

import jsonschema
import pkg_resources
import yaml

from dstack._internal.core.profile import Profile


def load_profiles() -> Dict[str, Profile]:
    # NOTE: This only supports local profiles
    profiles_path = Path(".dstack") / "profiles.yml"
    if not profiles_path.exists():
        profiles_path = Path(".dstack") / "profiles.yaml"
    if not profiles_path.exists():
        return {}
    else:
        with profiles_path.open("r") as f:
            profiles = yaml.load(f, yaml.FullLoader)
        schema = json.loads(
            pkg_resources.resource_string("dstack._internal", "schemas/profiles.json")
        )
        jsonschema.validate(profiles, schema)
        for profile in profiles["profiles"]:
            profile = Profile.parse_obj(profile)
            if profile.default:
                profiles[
                    "default"
                ] = profile  # we can't have Profile(name="default"), we use the latest default=True
            profiles[profile.name] = profile
    del profiles["profiles"]  # we can't have Profile(name="profiles")
    return profiles
