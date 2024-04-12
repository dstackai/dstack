import json
from typing import List

from dstack._internal.core.backends.base import Backend
from dstack._internal.core.backends.cudo import CudoBackend, CudoConfig, api_client
from dstack._internal.core.models.backends.base import (
    BackendType,
    ConfigElementValue,
    ConfigMultiElement,
)
from dstack._internal.core.models.backends.cudo import (
    CudoConfigInfo,
    CudoConfigInfoWithCreds,
    CudoConfigInfoWithCredsPartial,
    CudoConfigValues,
    CudoCreds,
    CudoStoredConfig,
)
from dstack._internal.server.models import BackendModel, ProjectModel
from dstack._internal.server.services.backends import Configurator
from dstack._internal.server.services.backends.configurators.base import (
    raise_invalid_credentials_error,
)

REGIONS = [
    "no-luster-1",
    "se-smedjebacken-1",
    "gb-london-1",
    "se-stockholm-1",
    "us-newyork-1",
    "us-santaclara-1",
]

DEFAULT_REGION = "no-luster-1"


class CudoConfigurator(Configurator):
    TYPE: BackendType = BackendType.CUDO

    def get_config_values(self, config: CudoConfigInfoWithCredsPartial) -> CudoConfigValues:
        config_values = CudoConfigValues()
        if config.creds is None:
            return config_values
        self._validate_cudo_api_key(config.creds.api_key)
        config_values.regions = self._get_regions_element(
            selected=config.regions or [DEFAULT_REGION]
        )
        return config_values

    def create_backend(
        self, project: ProjectModel, config: CudoConfigInfoWithCreds
    ) -> BackendModel:
        if config.regions is None:
            config.regions = REGIONS
        return BackendModel(
            project_id=project.id,
            type=self.TYPE.value,
            config=CudoStoredConfig(**CudoConfigInfo.__response__.parse_obj(config).dict()).json(),
            auth=CudoCreds.parse_obj(config.creds).json(),
        )

    def get_config_info(self, model: BackendModel, include_creds: bool) -> CudoConfigInfo:
        config = self._get_backend_config(model)
        if include_creds:
            return CudoConfigInfoWithCreds.__response__.parse_obj(config)
        return CudoConfigInfo.__response__.parse_obj(config)

    def get_backend(self, model: BackendModel) -> Backend:
        config = self._get_backend_config(model)
        return CudoBackend(config=config)

    def _get_regions_element(self, selected: List[str]) -> ConfigMultiElement:
        element = ConfigMultiElement(selected=selected)
        for r in REGIONS:
            element.values.append(ConfigElementValue(value=r, label=r))
        return element

    def _get_backend_config(self, model: BackendModel) -> CudoConfig:
        return CudoConfig.__response__(
            **json.loads(model.config),
            creds=CudoCreds.parse_raw(model.auth),
        )

    def _validate_cudo_api_key(self, api_key: str):
        client = api_client.CudoApiClient(api_key=api_key)
        if not client.validate_api_key():
            raise_invalid_credentials_error(fields=[["creds", "api_key"]])
