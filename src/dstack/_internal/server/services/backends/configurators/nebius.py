import json
from typing import List

import requests

import dstack._internal.core.backends.nebius.api_client as api_client
from dstack._internal.core.backends.base import Backend
from dstack._internal.core.backends.nebius import NebiusBackend
from dstack._internal.core.backends.nebius.config import NebiusConfig
from dstack._internal.core.models.backends.base import (
    BackendType,
    ConfigElementValue,
    ConfigMultiElement,
)
from dstack._internal.core.models.backends.nebius import (
    NebiusConfigInfo,
    NebiusConfigInfoWithCreds,
    NebiusConfigInfoWithCredsPartial,
    NebiusConfigValues,
    NebiusCreds,
    NebiusStoredConfig,
)
from dstack._internal.server.models import BackendModel, ProjectModel
from dstack._internal.server.services.backends import Configurator
from dstack._internal.server.services.backends.configurators.base import (
    raise_invalid_credentials_error,
)

REGIONS = ["eu-north1-c"]


class NebiusConfigurator(Configurator):
    TYPE: BackendType = BackendType.NEBIUS

    def get_config_values(self, config: NebiusConfigInfoWithCredsPartial) -> NebiusConfigValues:
        config_values = NebiusConfigValues()
        if config.creds is None:
            return config_values
        self._validate_nebius_creds(config.creds)
        # TODO(egor-s) cloud_id
        # TODO(egor-s) folder_id
        # TODO(egor-s) network_id
        config_values.regions = self._get_regions_element(selected=config.regions or [])
        return config_values

    def create_backend(
        self, project: ProjectModel, config: NebiusConfigInfoWithCreds
    ) -> BackendModel:
        if config.regions is None:
            config.regions = REGIONS
        self._validate_nebius_creds(config.creds)
        return BackendModel(
            project_id=project.id,
            type=self.TYPE.value,
            config=NebiusStoredConfig.__response__.parse_obj(config).json(),
            auth=NebiusCreds.parse_obj(config.creds).json(),
        )

    def get_config_info(self, model: BackendModel, include_creds: bool) -> NebiusConfigInfo:
        config = self._get_backend_config(model)
        if include_creds:
            return NebiusConfigInfoWithCreds.__response__.parse_obj(config)
        return NebiusConfigInfo.__response__.parse_obj(config)

    def get_backend(self, model: BackendModel) -> Backend:
        config = self._get_backend_config(model)
        return NebiusBackend(config=config)

    def _get_backend_config(self, model: BackendModel) -> NebiusConfig:
        return NebiusConfig.__response__(
            **json.loads(model.config),
            creds=NebiusCreds.parse_raw(model.auth),
        )

    def _validate_nebius_creds(self, creds: NebiusCreds):
        try:
            api_client.NebiusAPIClient(json.loads(creds.data)).get_token()
        except requests.HTTPError:
            raise_invalid_credentials_error(fields=[["creds", "data"]])

    def _get_regions_element(self, selected: List[str]) -> ConfigMultiElement:
        element = ConfigMultiElement(selected=selected)
        for r in REGIONS:
            element.values.append(ConfigElementValue(value=r, label=r))
        return element
