import json

import requests

import dstack._internal.core.backends.nebius.api_client as api_client
from dstack._internal.core.backends.nebius import NebiusBackend
from dstack._internal.core.backends.nebius.config import NebiusConfig
from dstack._internal.core.models.backends.base import (
    BackendType,
)
from dstack._internal.core.models.backends.nebius import (
    NebiusConfigInfo,
    NebiusConfigInfoWithCreds,
    NebiusCreds,
    NebiusStoredConfig,
)
from dstack._internal.server.services.backends.configurators.base import (
    Configurator,
    StoredBackendRecord,
    raise_invalid_credentials_error,
)

REGIONS = ["eu-north1-c"]


class NebiusConfigurator(Configurator):
    TYPE: BackendType = BackendType.NEBIUS

    def validate_config(self, config: NebiusConfigInfoWithCreds, default_creds_enabled: bool):
        self._validate_nebius_creds(config.creds)

    def create_backend(
        self, project_name: str, config: NebiusConfigInfoWithCreds
    ) -> StoredBackendRecord:
        if config.regions is None:
            config.regions = REGIONS
        return StoredBackendRecord(
            config=NebiusStoredConfig.__response__.parse_obj(config).json(),
            auth=NebiusCreds.parse_obj(config.creds).json(),
        )

    def get_config_info(
        self, record: StoredBackendRecord, include_creds: bool
    ) -> NebiusConfigInfo:
        config = self._get_backend_config(record)
        if include_creds:
            return NebiusConfigInfoWithCreds.__response__.parse_obj(config)
        return NebiusConfigInfo.__response__.parse_obj(config)

    def get_backend(self, record: StoredBackendRecord) -> NebiusBackend:
        config = self._get_backend_config(record)
        return NebiusBackend(config=config)

    def _get_backend_config(self, record: StoredBackendRecord) -> NebiusConfig:
        return NebiusConfig.__response__(
            **json.loads(record.config),
            creds=NebiusCreds.parse_raw(record.auth),
        )

    def _validate_nebius_creds(self, creds: NebiusCreds):
        try:
            api_client.NebiusAPIClient(json.loads(creds.data)).get_token()
        except requests.HTTPError:
            raise_invalid_credentials_error(fields=[["creds", "data"]])
