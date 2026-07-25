import json

from dstack._internal.core.backends.base.configurator import (
    BackendRecord,
    Configurator,
    raise_invalid_credentials_error,
)
from dstack._internal.core.backends.seeweb.api_client import SeewebApiClient
from dstack._internal.core.backends.seeweb.backend import SeewebBackend
from dstack._internal.core.backends.seeweb.models import (
    SeewebBackendConfig,
    SeewebBackendConfigWithCreds,
    SeewebConfig,
    SeewebCreds,
    SeewebStoredConfig,
)
from dstack._internal.core.models.backends.base import BackendType


class SeewebConfigurator(
    Configurator[
        SeewebBackendConfig,
        SeewebBackendConfigWithCreds,
    ]
):
    TYPE = BackendType.SEEWEB
    BACKEND_CLASS = SeewebBackend

    def validate_config(self, config: SeewebBackendConfigWithCreds, default_creds_enabled: bool):
        if not SeewebApiClient(config.creds.api_token).validate_api_key():
            raise_invalid_credentials_error(fields=[["creds", "api_token"]])

    def create_backend(
        self, project_name: str, config: SeewebBackendConfigWithCreds
    ) -> BackendRecord:
        return BackendRecord(
            config=SeewebStoredConfig(
                **SeewebBackendConfig.__response__.parse_obj(config).dict()
            ).json(),
            auth=SeewebCreds.parse_obj(config.creds).json(),
        )

    def get_backend_config_with_creds(self, record: BackendRecord) -> SeewebBackendConfigWithCreds:
        config = self._get_config(record)
        return SeewebBackendConfigWithCreds.__response__.parse_obj(config)

    def get_backend_config_without_creds(self, record: BackendRecord) -> SeewebBackendConfig:
        config = self._get_config(record)
        return SeewebBackendConfig.__response__.parse_obj(config)

    def get_backend(self, record: BackendRecord) -> SeewebBackend:
        config = self._get_config(record)
        return SeewebBackend(config=config)

    def _get_config(self, record: BackendRecord) -> SeewebConfig:
        return SeewebConfig.__response__(
            **json.loads(record.config),
            creds=SeewebCreds.parse_raw(record.auth),
        )
