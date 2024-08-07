import json
from typing import List

from dstack._internal.core.backends.base import Backend
from dstack._internal.core.backends.runpod import RunpodBackend, RunpodConfig, api_client
from dstack._internal.core.models.backends.base import (
    BackendType,
    ConfigElementValue,
    ConfigMultiElement,
)
from dstack._internal.core.models.backends.runpod import (
    RunpodConfigInfo,
    RunpodConfigInfoWithCreds,
    RunpodConfigInfoWithCredsPartial,
    RunpodConfigValues,
    RunpodCreds,
    RunpodStoredConfig,
)
from dstack._internal.server.models import BackendModel, ProjectModel
from dstack._internal.server.services.backends import Configurator
from dstack._internal.server.services.backends.configurators.base import (
    raise_invalid_credentials_error,
)

REGIONS = [
    "CA-MTL-1",
    "EU-NL-1",
    "EU-RO-1",
    "EU-SE-1",
    "EUR-IS-1",
    "EUR-IS-2",
    "EUR-NO-1",
    "US-OR-1",
]

DEFAULT_REGION = "CA-MTL-1"


class RunpodConfigurator(Configurator):
    TYPE: BackendType = BackendType.RUNPOD

    def get_config_values(self, config: RunpodConfigInfoWithCredsPartial) -> RunpodConfigValues:
        config_values = RunpodConfigValues()
        if config.creds is None:
            return config_values
        self._validate_runpod_api_key(config.creds.api_key)
        config_values.regions = self._get_regions_element(
            selected=config.regions or [DEFAULT_REGION]
        )
        return config_values

    def create_backend(
        self, project: ProjectModel, config: RunpodConfigInfoWithCreds
    ) -> BackendModel:
        if config.regions is None:
            config.regions = REGIONS
        return BackendModel(
            project_id=project.id,
            type=self.TYPE.value,
            config=RunpodStoredConfig(
                **RunpodConfigInfo.__response__.parse_obj(config).dict()
            ).json(),
            auth=RunpodCreds.parse_obj(config.creds).json(),
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
        element = ConfigMultiElement(selected=selected)
        for r in REGIONS:
            element.values.append(ConfigElementValue(value=r, label=r))
        return element

    def _get_backend_config(self, model: BackendModel) -> RunpodConfig:
        return RunpodConfig(
            **json.loads(model.config),
            creds=RunpodCreds.parse_raw(model.auth),
        )

    def _validate_runpod_api_key(self, api_key: str):
        client = api_client.RunpodApiClient(api_key=api_key)
        if not client.validate_api_key():
            raise_invalid_credentials_error(fields=[["creds", "api_key"]])
