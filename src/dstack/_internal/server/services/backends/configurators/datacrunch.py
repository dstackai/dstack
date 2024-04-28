import json
from typing import List

from dstack._internal.core.backends.datacrunch import DataCrunchBackend
from dstack._internal.core.backends.datacrunch.config import DataCrunchConfig
from dstack._internal.core.models.backends.base import (
    BackendType,
    ConfigElementValue,
    ConfigMultiElement,
)
from dstack._internal.core.models.backends.datacrunch import (
    AnyDataCrunchConfigInfo,
    DataCrunchConfigInfo,
    DataCrunchConfigInfoWithCreds,
    DataCrunchConfigInfoWithCredsPartial,
    DataCrunchConfigValues,
    DataCrunchCreds,
    DataCrunchStoredConfig,
)
from dstack._internal.server.models import BackendModel, ProjectModel
from dstack._internal.server.services.backends.configurators.base import Configurator

REGIONS = [
    "FIN-01",
    "ICE-01",
]

DEFAULT_REGION = "FIN-01"


class DataCrunchConfigurator(Configurator):
    TYPE: BackendType = BackendType.DATACRUNCH

    def get_config_values(
        self, config: DataCrunchConfigInfoWithCredsPartial
    ) -> DataCrunchConfigValues:
        config_values = DataCrunchConfigValues()
        if config.creds is None:
            return config_values
        config_values.regions = self._get_regions_element(
            selected=config.regions or [DEFAULT_REGION]
        )
        return config_values

    def create_backend(
        self, project: ProjectModel, config: DataCrunchConfigInfoWithCreds
    ) -> BackendModel:
        if config.regions is None:
            config.regions = REGIONS
        return BackendModel(
            project_id=project.id,
            type=self.TYPE.value,
            config=DataCrunchStoredConfig(
                **DataCrunchConfigInfo.__response__.parse_obj(config).dict()
            ).json(),
            auth=DataCrunchCreds.parse_obj(config.creds).json(),
        )

    def get_config_info(self, model: BackendModel, include_creds: bool) -> AnyDataCrunchConfigInfo:
        config = self._get_backend_config(model)
        if include_creds:
            return DataCrunchConfigInfoWithCreds.__response__.parse_obj(config)
        return DataCrunchConfigInfo.__response__.parse_obj(config)

    def get_backend(self, model: BackendModel) -> DataCrunchBackend:
        config = self._get_backend_config(model)
        return DataCrunchBackend(config=config)

    def _get_backend_config(self, model: BackendModel) -> DataCrunchConfig:
        return DataCrunchConfig.__response__(
            **json.loads(model.config),
            creds=DataCrunchCreds.parse_raw(model.auth),
        )

    def _get_regions_element(self, selected: List[str]) -> ConfigMultiElement:
        element = ConfigMultiElement(selected=selected)
        for r in REGIONS:
            element.values.append(ConfigElementValue(value=r, label=r))
        return element
