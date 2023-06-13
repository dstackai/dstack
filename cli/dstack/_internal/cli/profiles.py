import json
from pathlib import Path
from typing import Any, Dict, Optional

import jsonschema
import pkg_resources
import yaml


def load_profiles() -> Optional[Dict[str, Dict[str, Any]]]:
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
            pkg_resources.resource_string("dstack._internal.schemas", "profiles.json")
        )
        jsonschema.validate(profiles, schema)
        for profile in profiles["profiles"]:
            if profile.get("default"):
                profiles["default"] = profile
            profiles[profile["name"]] = profile
    del profiles["profiles"]
    return profiles
