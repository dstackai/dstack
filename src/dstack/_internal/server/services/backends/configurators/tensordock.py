import json
from typing import List

from dstack._internal.core.backends.tensordock import TensorDockBackend, api_client
from dstack._internal.core.backends.tensordock.config import TensorDockConfig
from dstack._internal.core.models.backends.base import (
    BackendType,
    ConfigElementValue,
    ConfigMultiElement,
)
from dstack._internal.core.models.backends.tensordock import (
    AnyTensorDockConfigInfo,
    TensorDockConfigInfo,
    TensorDockConfigInfoWithCreds,
    TensorDockConfigInfoWithCredsPartial,
    TensorDockConfigValues,
    TensorDockCreds,
    TensorDockStoredConfig,
)
from dstack._internal.server.models import BackendModel, ProjectModel
from dstack._internal.server.services.backends.configurators.base import (
    Configurator,
    raise_invalid_credentials_error,
)

# TensorDock regions are dynamic, currently we don't offer any filtering
REGIONS = []


class TensorDockConfigurator(Configurator):
    TYPE: BackendType = BackendType.TENSORDOCK

    def get_config_values(
        self, config: TensorDockConfigInfoWithCredsPartial
    ) -> TensorDockConfigValues:
        config_values = TensorDockConfigValues()
        if config.creds is None:
            return config_values
        self._validate_tensordock_creds(config.creds.api_key, config.creds.api_token)
        config_values.regions = self._get_regions_element(selected=config.regions or [])
        return config_values

    def create_backend(
        self, project: ProjectModel, config: TensorDockConfigInfoWithCreds
    ) -> BackendModel:
        if config.regions is None:
            config.regions = REGIONS
        return BackendModel(
            project_id=project.id,
            type=self.TYPE.value,
            config=TensorDockStoredConfig(
                **TensorDockConfigInfo.__response__.parse_obj(config).dict()
            ).json(),
            auth=TensorDockCreds.parse_obj(config.creds).json(),
        )

    def get_config_info(self, model: BackendModel, include_creds: bool) -> AnyTensorDockConfigInfo:
        config = self._get_backend_config(model)
        if include_creds:
            return TensorDockConfigInfoWithCreds.__response__.parse_obj(config)
        return TensorDockConfigInfo.__response__.parse_obj(config)

    def get_backend(self, model: BackendModel) -> TensorDockBackend:
        config = self._get_backend_config(model)
        return TensorDockBackend(config=config)

    def _get_backend_config(self, model: BackendModel) -> TensorDockConfig:
        return TensorDockConfig.__response__(
            **json.loads(model.config),
            creds=TensorDockCreds.parse_raw(model.auth),
        )

    def _validate_tensordock_creds(self, api_key: str, api_token: str):
        client = api_client.TensorDockAPIClient(api_key=api_key, api_token=api_token)
        if not client.auth_test():
            raise_invalid_credentials_error(fields=[["creds", "api_key"], ["creds", "api_token"]])

    def _get_regions_element(self, selected: List[str]) -> ConfigMultiElement:
        element = ConfigMultiElement(selected=selected)
        for r in REGIONS:
            element.values.append(ConfigElementValue(value=r, label=r))
        return element
