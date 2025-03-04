import json
from typing import List

from dstack._internal.core.backends.base import Backend
from dstack._internal.core.backends.runpod import RunpodBackend, RunpodConfig, api_client
from dstack._internal.core.models.backends.base import BackendType, ConfigMultiElement
from dstack._internal.core.models.backends.runpod import (
    RunpodConfigInfo,
    RunpodConfigInfoWithCreds,
    RunpodConfigInfoWithCredsPartial,
    RunpodConfigValues,
    RunpodCreds,
    RunpodStoredConfig,
)
from dstack._internal.server.models import BackendModel, DecryptedString, ProjectModel
from dstack._internal.server.services.backends import Configurator
from dstack._internal.server.services.backends.configurators.base import (
    raise_invalid_credentials_error,
)


class RunpodConfigurator(Configurator):
    TYPE: BackendType = BackendType.RUNPOD

    def get_config_values(self, config: RunpodConfigInfoWithCredsPartial) -> RunpodConfigValues:
        config_values = RunpodConfigValues()
        if config.creds is None:
            return config_values
        self._validate_runpod_api_key(config.creds.api_key)
        config_values.regions = self._get_regions_element(selected=config.regions or [])
        return config_values

    def create_backend(
        self, project: ProjectModel, config: RunpodConfigInfoWithCreds
    ) -> BackendModel:
        return BackendModel(
            project_id=project.id,
            type=self.TYPE.value,
            config=RunpodStoredConfig(
                **RunpodConfigInfo.__response__.parse_obj(config).dict()
            ).json(),
            auth=DecryptedString(plaintext=RunpodCreds.parse_obj(config.creds).json()),
        )

    def get_config_info(self, model: BackendModel, include_creds: bool) -> RunpodConfigInfo:
        config = self._get_backend_config(model)
        if include_creds:
            return RunpodConfigInfoWithCreds.__response__.parse_obj(config)
        return RunpodConfigInfo.__response__.parse_obj(config)

    def get_backend(self, model: BackendModel) -> Backend:
        config = self._get_backend_config(model)
        return RunpodBackend(config=config)

    def _get_regions_element(self, selected: List[str]) -> ConfigMultiElement:
        return ConfigMultiElement(selected=selected)

    def _get_backend_config(self, model: BackendModel) -> RunpodConfig:
        return RunpodConfig(
            **json.loads(model.config),
            creds=RunpodCreds.parse_raw(model.auth.get_plaintext_or_error()),
        )

    def _validate_runpod_api_key(self, api_key: str):
        client = api_client.RunpodApiClient(api_key=api_key)
        if not client.validate_api_key():
            raise_invalid_credentials_error(fields=[["creds", "api_key"]])
