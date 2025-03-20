import json

from dstack._internal.core.backends.base.configurator import (
    BackendRecord,
    Configurator,
    raise_invalid_credentials_error,
)
from dstack._internal.core.backends.cudo import api_client
from dstack._internal.core.backends.cudo.backend import CudoBackend
from dstack._internal.core.backends.cudo.models import (
    AnyCudoBackendConfig,
    CudoBackendConfig,
    CudoBackendConfigWithCreds,
    CudoConfig,
    CudoCreds,
    CudoStoredConfig,
)
from dstack._internal.core.models.backends.base import BackendType

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
    TYPE = BackendType.CUDO
    BACKEND_CLASS = CudoBackend

    def validate_config(self, config: CudoBackendConfigWithCreds, default_creds_enabled: bool):
        self._validate_cudo_api_key(config.creds.api_key)

    def create_backend(
        self, project_name: str, config: CudoBackendConfigWithCreds
    ) -> BackendRecord:
        if config.regions is None:
            config.regions = REGIONS
        return BackendRecord(
            config=CudoStoredConfig(
                **CudoBackendConfig.__response__.parse_obj(config).dict()
            ).json(),
            auth=CudoCreds.parse_obj(config.creds).json(),
        )

    def get_backend_config(
        self, record: BackendRecord, include_creds: bool
    ) -> AnyCudoBackendConfig:
        config = self._get_config(record)
        if include_creds:
            return CudoBackendConfigWithCreds.__response__.parse_obj(config)
        return CudoBackendConfig.__response__.parse_obj(config)

    def get_backend(self, record: BackendRecord) -> CudoBackend:
        config = self._get_config(record)
        return CudoBackend(config=config)

    def _get_config(self, record: BackendRecord) -> CudoConfig:
        return CudoConfig.__response__(
            **json.loads(record.config),
            creds=CudoCreds.parse_raw(record.auth),
        )

    def _validate_cudo_api_key(self, api_key: str):
        client = api_client.CudoApiClient(api_key=api_key)
        if not client.validate_api_key():
            raise_invalid_credentials_error(fields=[["creds", "api_key"]])
