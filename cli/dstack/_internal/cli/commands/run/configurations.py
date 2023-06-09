import json
import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import jsonschema
import pkg_resources
import yaml

from dstack._internal.cli.common import console
from dstack._internal.cli.profiles import load_profiles
from dstack._internal.providers.extensions import NoVSCodeVersionError, VSCodeDesktopServer


def _init_base_provider_data(configuration_data: Dict[str, Any], provider_data: Dict[str, Any]):
    if "cache" in configuration_data:
        provider_data["cache"] = configuration_data["cache"]
    if "ports" in configuration_data:
        provider_data["ports"] = configuration_data["ports"]
    if "python" in configuration_data:
        provider_data["python"] = configuration_data["python"]
    if "env" in configuration_data:
        provider_data["env"] = configuration_data["env"]


def _parse_dev_environment_configuration_data(
    configuration_data: Dict[str, Any]
) -> Tuple[str, Dict[str, Any]]:
    provider_name = "ssh"
    provider_data = {}
    _init_base_provider_data(configuration_data, provider_data)
    provider_data["setup"] = []
    try:
        VSCodeDesktopServer.patch_setup(
            provider_data["setup"],
            vscode_extensions=[
                "ms-python.python",
                "ms-toolsai.jupyter",
            ],
        )
    except NoVSCodeVersionError as e:
        console.print(
            "[grey58]Unable to detect the VS Code version and pre-install extensions. Fix by opening ["
            "sea_green3]Command Palette[/sea_green3], executing [sea_green3]Shell Command: Install 'code' command in "
            "PATH[/sea_green3], and restarting terminal.[/]\n"
        )
    provider_data["setup"].append("pip install -q --no-cache-dir ipykernel")
    provider_data["setup"].extend(configuration_data.get("setup") or [])
    return provider_name, provider_data


def _parse_task_configuration_data(
    configuration_data: Dict[str, Any]
) -> Tuple[str, Dict[str, Any]]:
    # TODO: Support the `docker` provider
    provider_name = "bash"
    provider_data = {"commands": []}
    if "setup" in configuration_data:
        provider_data["setup"] = configuration_data["setup"] or []
    provider_data["commands"].extend(configuration_data["commands"])
    _init_base_provider_data(configuration_data, provider_data)
    return provider_name, provider_data


def parse_configuration_file(
    working_dir: str, file_name: Optional[str], profile_name: Optional[str]
) -> Tuple[str, str, Dict[str, Any], Optional[str]]:
    configuration_path = Path(file_name) if file_name else Path(working_dir) / ".dstack.yml"
    if not file_name and not configuration_path.exists():
        configuration_path = Path(working_dir) / ".dstack.yaml"
    if not configuration_path.exists():
        exit(f"Error: No such configuration file {configuration_path}")
    with configuration_path.open("r") as f:
        configuration_data = yaml.load(f, yaml.FullLoader)
    schema = json.loads(
        pkg_resources.resource_string("dstack._internal.schemas", "configuration.json")
    )
    jsonschema.validate(configuration_data, schema)
    configuration_type = configuration_data["type"]
    if configuration_type == "dev-environment":
        (provider_name, provider_data) = _parse_dev_environment_configuration_data(
            configuration_data
        )
    elif configuration_type == "task":
        (provider_name, provider_data) = _parse_task_configuration_data(configuration_data)
    else:
        exit(f"Unsupported configuration type: {configuration_type}")
    profiles = load_profiles()
    if profile_name:
        if profile_name in profiles:
            profile = profiles[profile_name]
        else:
            exit(f"Error: No profile `{profile_name}` found")
    else:
        profile = profiles.get("default")
    if profile and "resources" in profile:
        provider_data["resources"] = profile["resources"]
        provider_data["resources"]["interruptible"] = True
        if "instance-type" in profile["resources"]:
            if profile["resources"]["instance-type"] == "on-demand":
                del provider_data["resources"]["interruptible"]
                # TODO: It doesn't support instance-type properly
            del provider_data["resources"]["instance-type"]
    project_name = profile.get("project") if profile else None
    if not Path(os.getcwd()).samefile(Path(working_dir)):
        provider_data["working_dir"] = str(Path(working_dir))
    return str(configuration_path), provider_name, provider_data, project_name
