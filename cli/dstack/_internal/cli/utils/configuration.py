from pathlib import Path
from typing import Optional

import pydantic
import yaml

from dstack._internal.cli.profiles import load_profiles
from dstack._internal.configurators import JobConfigurator
from dstack._internal.configurators.dev_environment import DevEnvironmentConfigurator
from dstack._internal.configurators.task import TaskConfigurator
from dstack._internal.core.configuration import (
    DevEnvironmentConfiguration,
    TaskConfiguration,
    parse,
)


def load_configuration(
    working_dir: str, configuration_path: Optional[str], profile_name: Optional[str]
) -> JobConfigurator:
    configuration_path = resolve_configuration_path(configuration_path, working_dir)
    try:
        configuration = parse(yaml.safe_load(configuration_path.read_text()))
        profiles = load_profiles()
    except pydantic.ValidationError as e:
        exit(e)

    if profile_name:
        try:
            profile = profiles.get(profile_name)
        except KeyError:
            exit(f"Error: No profile `{profile_name}` found")
    else:
        profile = profiles.default()

    if isinstance(configuration, DevEnvironmentConfiguration):
        return DevEnvironmentConfigurator(
            working_dir, str(configuration_path), configuration, profile
        )
    elif isinstance(configuration, TaskConfiguration):
        return TaskConfigurator(working_dir, str(configuration_path), configuration, profile)
    exit(f"Unsupported configuration {type(configuration)}")


def resolve_configuration_path(file_name: str, working_dir: str) -> Path:
    root = Path.cwd()
    configuration_path = root / file_name if file_name else root / working_dir / ".dstack.yml"
    if not file_name and not configuration_path.exists():
        configuration_path = root / working_dir / ".dstack.yaml"
    if not configuration_path.exists():
        exit(f"Error: No such configuration file {configuration_path}")
    try:
        return configuration_path.relative_to(root)
    except ValueError:
        exit(f"Configuration file is outside the repository {root}")
