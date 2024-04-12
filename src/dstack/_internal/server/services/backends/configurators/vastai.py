import json
from typing import List

from dstack._internal.core.backends.vastai import VastAIBackend, api_client
from dstack._internal.core.backends.vastai.config import VastAIConfig
from dstack._internal.core.models.backends.base import (
    BackendType,
    ConfigElementValue,
    ConfigMultiElement,
)
from dstack._internal.core.models.backends.vastai import (
    AnyVastAIConfigInfo,
    VastAIConfigInfo,
    VastAIConfigInfoWithCreds,
    VastAIConfigInfoWithCredsPartial,
    VastAIConfigValues,
    VastAICreds,
    VastAIStoredConfig,
)
from dstack._internal.server.models import BackendModel, ProjectModel
from dstack._internal.server.services.backends.configurators.base import (
    Configurator,
    raise_invalid_credentials_error,
)

# VastAI regions are dynamic, currently we don't offer any filtering
REGIONS = []


class VastAIConfigurator(Configurator):
    TYPE: BackendType = BackendType.VASTAI

    def get_config_values(self, config: VastAIConfigInfoWithCredsPartial) -> VastAIConfigValues:
        config_values = VastAIConfigValues()
        if config.creds is None:
            return config_values
        self._validate_vastai_creds(config.creds.api_key)
        config_values.regions = self._get_regions_element(selected=config.regions or [])
        return config_values

    def create_backend(
        self, project: ProjectModel, config: VastAIConfigInfoWithCreds
    ) -> BackendModel:
        if config.regions is None:
            config.regions = REGIONS
        return BackendModel(
            project_id=project.id,
            type=self.TYPE.value,
            config=VastAIStoredConfig(
                **VastAIConfigInfo.__response__.parse_obj(config).dict()
            ).json(),
            auth=VastAICreds.parse_obj(config.creds).json(),
        )

    def get_config_info(self, model: BackendModel, include_creds: bool) -> AnyVastAIConfigInfo:
        config = self._get_backend_config(model)
        if include_creds:
            return VastAIConfigInfoWithCreds.__response__.parse_obj(config)
        return VastAIConfigInfo.__response__.parse_obj(config)

    def get_backend(self, model: BackendModel) -> VastAIBackend:
        config = self._get_backend_config(model)
        return VastAIBackend(config=config)

    def _get_backend_config(self, model: BackendModel) -> VastAIConfig:
        return VastAIConfig.__response__(
            **json.loads(model.config),
            creds=VastAICreds.parse_raw(model.auth),
        )

    def _validate_vastai_creds(self, api_key: str):
        client = api_client.VastAIAPIClient(api_key=api_key)
        if not client.auth_test():
            raise_invalid_credentials_error(fields=[["creds", "api_key"]])

    def _get_regions_element(self, selected: List[str]) -> ConfigMultiElement:
        element = ConfigMultiElement(selected=selected)
        for r in REGIONS:
            element.values.append(ConfigElementValue(value=r, label=r))
        return element
