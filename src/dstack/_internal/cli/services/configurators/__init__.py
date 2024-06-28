from pathlib import Path
from typing import Dict, Optional, Type

import yaml

from dstack._internal.cli.services.configurators.base import BaseApplyConfigurator
from dstack._internal.cli.services.configurators.gateway import GatewayConfigurator
from dstack._internal.cli.services.configurators.volume import VolumeConfigurator
from dstack._internal.core.errors import ConfigurationError
from dstack._internal.core.models.configurations import (
    AnyApplyConfiguration,
    ApplyConfigurationType,
    parse_apply_configuration,
)

apply_configurators_mapping: Dict[ApplyConfigurationType, Type[BaseApplyConfigurator]] = {
    cls.TYPE: cls for cls in [GatewayConfigurator, VolumeConfigurator]
}


def get_apply_configurator_class(configurator_type: str) -> Type[BaseApplyConfigurator]:
    return apply_configurators_mapping[ApplyConfigurationType(configurator_type)]


def load_apply_configuration(configuration_file: Optional[str]) -> AnyApplyConfiguration:
    if configuration_file is None:
        configuration_path = Path.cwd() / ".dstack.yml"
        if not configuration_path.exists():
            configuration_path = configuration_path.with_suffix(".yaml")
        if not configuration_path.exists():
            raise ConfigurationError(
                "No configuration file specified via `-f` and no default .dstack.yml configuration found"
            )
    else:
        configuration_path = Path(configuration_file)
        if not configuration_path.exists():
            raise ConfigurationError(f"Configuration file {configuration_file} does not exist")
    try:
        with open(configuration_path, "r") as f:
            conf = parse_apply_configuration(yaml.safe_load(f))
    except OSError:
        raise ConfigurationError(f"Failed to load configuration from {configuration_path}")
    return conf
