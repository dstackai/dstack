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
    provider_data["build"] = configuration_data.get("build") or []


def _parse_dev_environment_configuration_data(
    configuration_data: Dict[str, Any]
) -> Tuple[str, Dict[str, Any]]:
    provider_name = "ssh"
    provider_data = {
        "configuration_type": "dev-environment",
        "optional_build": [],
        "commands": [],
    }
    _init_base_provider_data(configuration_data, provider_data)
    try:
        extensions = ["ms-python.python", "ms-toolsai.jupyter"]
        VSCodeDesktopServer.patch_setup(
            provider_data["optional_build"], vscode_extensions=extensions
        )
        VSCodeDesktopServer.patch_commands(provider_data["commands"], vscode_extensions=extensions)
    except NoVSCodeVersionError as e:
        console.print(
            "[grey58]Unable to detect the VS Code version and pre-install extensions. Fix by opening ["
            "sea_green3]Command Palette[/sea_green3], executing [sea_green3]Shell Command: Install 'code' command in "
            "PATH[/sea_green3], and restarting terminal.[/]\n"
        )
    for key in ["optional_build", "commands"]:
        provider_data[key].append("pip install -q --no-cache-dir ipykernel")
    provider_data["commands"].extend(configuration_data.get("init") or [])
    return provider_name, provider_data


def _parse_task_configuration_data(
    configuration_data: Dict[str, Any]
) -> Tuple[str, Dict[str, Any]]:
    # TODO: Support the `docker` provider
    provider_name = "bash"
    provider_data = {
        "configuration_type": "task",
        "commands": [],
    }
    _init_base_provider_data(configuration_data, provider_data)
    provider_data["commands"].extend(configuration_data["commands"])
    return provider_name, provider_data


def parse_configuration_file(
    working_dir: str, file_name: Optional[str], profile_name: Optional[str]
) -> Tuple[str, str, Dict[str, Any], Optional[str]]:
    configuration_path = get_configuration_path(working_dir, file_name)
    with configuration_path.open("r") as f:
        configuration_data = yaml.load(f, yaml.FullLoader)
    schema = json.loads(
        pkg_resources.resource_string("dstack._internal", "schemas/configuration.json")
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
        profile = profiles.get("default", {})
    if "resources" in profile:
        provider_data["resources"] = profile["resources"]
    provider_data["spot_policy"] = profile.get("spot_policy")
    provider_data["retry_policy"] = profile.get("retry_policy")
    project_name = profile.get("project")
    if not Path(os.getcwd()).samefile(Path(working_dir)):
        provider_data["working_dir"] = str(Path(working_dir))
    return str(configuration_path), provider_name, provider_data, project_name


def get_configuration_path(working_dir: str, file_name: str) -> Path:
    configuration_path = Path(file_name) if file_name else Path(working_dir) / ".dstack.yml"
    if not file_name and not configuration_path.exists():
        configuration_path = Path(working_dir) / ".dstack.yaml"
    if not configuration_path.exists():
        exit(f"Error: No such configuration file {configuration_path}")
    return configuration_path
