import json

import requests

import dstack._internal.core.backends.nebius.api_client as api_client
from dstack._internal.core.backends.base.configurator import (
    BackendRecord,
    Configurator,
    raise_invalid_credentials_error,
)
from dstack._internal.core.backends.nebius.backend import NebiusBackend
from dstack._internal.core.backends.nebius.config import NebiusConfig
from dstack._internal.core.backends.nebius.models import (
    NebiusBackendConfig,
    NebiusBackendConfigWithCreds,
    NebiusCreds,
    NebiusStoredConfig,
)
from dstack._internal.core.models.backends.base import (
    BackendType,
)

REGIONS = ["eu-north1-c"]


class NebiusConfigurator(Configurator):
    TYPE: BackendType = BackendType.NEBIUS

    def validate_config(self, config: NebiusBackendConfigWithCreds, default_creds_enabled: bool):
        self._validate_nebius_creds(config.creds)

    def create_backend(
        self, project_name: str, config: NebiusBackendConfigWithCreds
    ) -> BackendRecord:
        if config.regions is None:
            config.regions = REGIONS
        return BackendRecord(
            config=NebiusStoredConfig.__response__.parse_obj(config).json(),
            auth=NebiusCreds.parse_obj(config.creds).json(),
        )

    def get_backend_config(
        self, record: BackendRecord, include_creds: bool
    ) -> NebiusBackendConfig:
        config = self._get_config(record)
        if include_creds:
            return NebiusBackendConfigWithCreds.__response__.parse_obj(config)
        return NebiusBackendConfig.__response__.parse_obj(config)

    def get_backend(self, record: BackendRecord) -> NebiusBackend:
        config = self._get_config(record)
        return NebiusBackend(config=config)

    def _get_config(self, record: BackendRecord) -> NebiusConfig:
        return NebiusConfig.__response__(
            **json.loads(record.config),
            creds=NebiusCreds.parse_raw(record.auth),
        )

    def _validate_nebius_creds(self, creds: NebiusCreds):
        try:
            api_client.NebiusAPIClient(json.loads(creds.data)).get_token()
        except requests.HTTPError:
            raise_invalid_credentials_error(fields=[["creds", "data"]])
