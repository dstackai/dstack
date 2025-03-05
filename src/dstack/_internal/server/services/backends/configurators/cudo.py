import json

from dstack._internal.core.backends.cudo import CudoBackend, CudoConfig, api_client
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.backends.cudo import (
    CudoConfigInfo,
    CudoConfigInfoWithCreds,
    CudoCreds,
    CudoStoredConfig,
)
from dstack._internal.server.services.backends.configurators.base import (
    Configurator,
    StoredBackendRecord,
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

    def validate_config(self, config: CudoConfigInfoWithCreds, default_creds_enabled: bool):
        self._validate_cudo_api_key(config.creds.api_key)

    def create_backend(
        self, project_name: str, config: CudoConfigInfoWithCreds
    ) -> StoredBackendRecord:
        if config.regions is None:
            config.regions = REGIONS
        return StoredBackendRecord(
            config=CudoStoredConfig(**CudoConfigInfo.__response__.parse_obj(config).dict()).json(),
            auth=CudoCreds.parse_obj(config.creds).json(),
        )

    def get_config_info(self, record: StoredBackendRecord, include_creds: bool) -> CudoConfigInfo:
        config = self._get_backend_config(record)
        if include_creds:
            return CudoConfigInfoWithCreds.__response__.parse_obj(config)
        return CudoConfigInfo.__response__.parse_obj(config)

    def get_backend(self, record: StoredBackendRecord) -> CudoBackend:
        config = self._get_backend_config(record)
        return CudoBackend(config=config)

    def _get_backend_config(self, record: StoredBackendRecord) -> CudoConfig:
        return CudoConfig.__response__(
            **json.loads(record.config),
            creds=CudoCreds.parse_raw(record.auth),
        )

    def _validate_cudo_api_key(self, api_key: str):
        client = api_client.CudoApiClient(api_key=api_key)
        if not client.validate_api_key():
            raise_invalid_credentials_error(fields=[["creds", "api_key"]])
