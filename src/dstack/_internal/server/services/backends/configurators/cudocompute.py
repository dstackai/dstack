import json
from typing import List

from dstack._internal.core.backends.base import Backend
from dstack._internal.core.backends.cudocompute import CudoComputeBackend, CudoComputeConfig
from dstack._internal.core.models.backends import (
    CudoComputeConfigInfo,
    CudoComputeConfigInfoWithCreds,
    CudoComputeConfigInfoWithCredsPartial,
    CudoComputeConfigValues,
)
from dstack._internal.core.models.backends.base import (
    BackendType,
    ConfigElementValue,
    ConfigMultiElement,
)
from dstack._internal.core.models.backends.cudocompute import (
    CudoComputeCreds,
    CudoComputeStoredConfig,
)
from dstack._internal.server.models import BackendModel, ProjectModel
from dstack._internal.server.services.backends import Configurator

REGIONS = [
    "no-luster-1",
    "se-smedjebacken-1",
    "gb-london-1",
    "se-stockholm-1",
    "us-newyork-1",
    "us-santaclara-1",
]

DEFAULT_REGION = "no-luster-1"


class CudoComputeConfigurator(Configurator):
    TYPE: BackendType = BackendType.CUDOCOMPUTE

    def get_default_configs(self) -> List[CudoComputeConfigInfoWithCreds]:
        return []

    def get_config_values(
        self, config: CudoComputeConfigInfoWithCredsPartial
    ) -> CudoComputeConfigValues:
        config_values = CudoComputeConfigValues()
        if config.creds is None:
            return config_values
        config_values.regions = self._get_regions_element(
            selected=config.regions or [DEFAULT_REGION]
        )
        return config_values

    def create_backend(
        self, project: ProjectModel, config: CudoComputeConfigInfoWithCreds
    ) -> BackendModel:
        if config.regions is None:
            config.regions = REGIONS
        return BackendModel(
            project_id=project.id,
            type=self.TYPE.value,
            config=CudoComputeStoredConfig(
                **CudoComputeConfigInfo.parse_obj(config).dict()
            ).json(),
            auth=CudoComputeCreds.parse_obj(config.creds).json(),
        )

    def get_config_info(self, model: BackendModel, include_creds: bool) -> CudoComputeConfigInfo:
        config = self._get_backend_config(model)
        if include_creds:
            return CudoComputeConfigInfoWithCreds.parse_obj(config)
        return CudoComputeConfigInfo.parse_obj(config)

    def get_backend(self, model: BackendModel) -> Backend:
        config = self._get_backend_config(model)
        return CudoComputeBackend(config=config)

    def _get_regions_element(self, selected: List[str]) -> ConfigMultiElement:
        element = ConfigMultiElement(selected=selected)
        for r in REGIONS:
            element.values.append(ConfigElementValue(value=r, label=r))
        return element

    def _get_backend_config(self, model: BackendModel) -> CudoComputeConfig:
        return CudoComputeConfig(
            **json.loads(model.config),
            creds=CudoComputeCreds.parse_raw(model.auth),
        )
