import sys
from pathlib import Path
from typing import Dict, Optional, Tuple, Type

import yaml

from dstack._internal.cli.services.configurators.base import (
    APPLY_STDIN_NAME,
    BaseApplyConfigurator,
)
from dstack._internal.cli.services.configurators.fleet import FleetConfigurator
from dstack._internal.cli.services.configurators.gateway import GatewayConfigurator
from dstack._internal.cli.services.configurators.preset import PresetConfigurator
from dstack._internal.cli.services.configurators.run import (
    BaseRunConfigurator,
    DevEnvironmentConfigurator,
    ServiceConfigurator,
    TaskConfigurator,
)
from dstack._internal.cli.services.configurators.volume import VolumeConfigurator
from dstack._internal.core.errors import ConfigurationError
from dstack._internal.core.models.configurations import (
    AnyApplyConfiguration,
    ApplyConfigurationType,
    parse_apply_configuration,
)

apply_configurators_mapping: Dict[
    ApplyConfigurationType, Type[BaseApplyConfigurator[AnyApplyConfiguration]]
] = {
    cls.TYPE: cls
    for cls in [
        DevEnvironmentConfigurator,
        TaskConfigurator,
        ServiceConfigurator,
        FleetConfigurator,
        GatewayConfigurator,
        VolumeConfigurator,
        PresetConfigurator,
    ]
}


run_configurators_mapping: Dict[ApplyConfigurationType, Type[BaseRunConfigurator]] = {
    cls.TYPE: cls
    for cls in [
        DevEnvironmentConfigurator,
        TaskConfigurator,
        ServiceConfigurator,
    ]
}


def get_apply_configurator_class(
    configurator_type: str,
) -> Type[BaseApplyConfigurator[AnyApplyConfiguration]]:
    return apply_configurators_mapping[ApplyConfigurationType(configurator_type)]


def get_run_configurator_class(configurator_type: str) -> Type[BaseRunConfigurator]:
    return run_configurators_mapping[ApplyConfigurationType(configurator_type)]


def load_apply_configuration(
    configuration_file: Optional[str],
) -> Tuple[str, AnyApplyConfiguration]:
    """
    Loads and parses the configuration for `dstack apply` and `dstack delete`.

    Args:
        configuration_file: The `-f` argument as passed by the user: a path to the configuration
            file, absolute or relative to the current directory, or `-` to read from stdin.
            If `None`, `.dstack.yml` or `.dstack.yaml` in the current directory is used.

    Returns:
        The configuration path and the parsed configuration. The configuration path is relative
        to the current directory if the file is under it, and absolute otherwise; `-` for stdin.
        It's shown to the user and sent to the server as part of the spec. Its parent directory
        is the base for relative paths in the configuration, such as `repos` and `files`.
    """
    if configuration_file is None:
        configuration_path = Path.cwd() / ".dstack.yml"
        if not configuration_path.exists():
            configuration_path = configuration_path.with_suffix(".yaml")
        if not configuration_path.exists():
            raise ConfigurationError(
                "No configuration file specified via `-f` and no default .dstack.yml configuration found"
            )
    elif configuration_file == APPLY_STDIN_NAME:
        configuration_path = sys.stdin.fileno()
    else:
        configuration_path = Path(configuration_file)
        if not configuration_path.exists():
            raise ConfigurationError(f"Configuration file {configuration_file} does not exist")
    try:
        with open(configuration_path, "r") as f:
            conf = parse_apply_configuration(yaml.safe_load(f))
    except OSError:
        raise ConfigurationError(f"Failed to load configuration from {configuration_path}")
    if isinstance(configuration_path, int):
        return APPLY_STDIN_NAME, conf
    absolute_path = configuration_path.absolute()
    cwd = Path.cwd()
    if absolute_path.is_relative_to(cwd):
        return str(absolute_path.relative_to(cwd)), conf
    return str(absolute_path), conf
