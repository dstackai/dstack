from typing import Dict, Type

from dstack._internal.cli.services.configurators.base import BaseApplyConfigurator
from dstack._internal.cli.services.configurators.gateway import GatewayConfigurator
from dstack._internal.core.models.configurations import ApplyConfigurationType

apply_configurators_mapping: Dict[ApplyConfigurationType, Type[BaseApplyConfigurator]] = {
    cls.TYPE: cls for cls in [GatewayConfigurator]
}


def get_apply_configurator_class(configurator_type: str) -> Type[BaseApplyConfigurator]:
    return apply_configurators_mapping[ApplyConfigurationType(configurator_type)]
