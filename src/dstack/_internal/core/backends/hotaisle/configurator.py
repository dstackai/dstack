import json

from dstack._internal.core.backends.base.configurator import (
    BackendRecord,
    Configurator,
)
from dstack._internal.core.backends.hotaisle.api_client import HotAisleAPIClient
from dstack._internal.core.backends.hotaisle.backend import HotAisleBackend
from dstack._internal.core.backends.hotaisle.models import (
    AnyHotAisleCreds,
    HotAisleBackendConfig,
    HotAisleBackendConfigWithCreds,
    HotAisleConfig,
    HotAisleCreds,
    HotAisleStoredConfig,
)
from dstack._internal.core.models.backends.base import (
    BackendType,
)
from dstack._internal.core.models.common import validate_extra_ignore, validate_json_extra_ignore


class HotAisleConfigurator(
    Configurator[
        HotAisleBackendConfig,
        HotAisleBackendConfigWithCreds,
    ]
):
    TYPE = BackendType.HOTAISLE
    BACKEND_CLASS = HotAisleBackend

    def validate_config(self, config: HotAisleBackendConfigWithCreds, default_creds_enabled: bool):
        self._validate_creds(config.creds, config.team_handle)

    def create_backend(
        self, project_name: str, config: HotAisleBackendConfigWithCreds
    ) -> BackendRecord:
        return BackendRecord(
            config=HotAisleStoredConfig(
                **validate_extra_ignore(HotAisleBackendConfig, config).dict()
            ).json(),
            auth=HotAisleCreds.model_validate(config.creds).json(),
        )

    def get_backend_config_with_creds(
        self, record: BackendRecord
    ) -> HotAisleBackendConfigWithCreds:
        config = self._get_config(record)
        return validate_extra_ignore(HotAisleBackendConfigWithCreds, config)

    def get_backend_config_without_creds(self, record: BackendRecord) -> HotAisleBackendConfig:
        config = self._get_config(record)
        return validate_extra_ignore(HotAisleBackendConfig, config)

    def get_backend(self, record: BackendRecord) -> HotAisleBackend:
        config = self._get_config(record)
        return HotAisleBackend(config=config)

    def _get_config(self, record: BackendRecord) -> HotAisleConfig:
        return validate_extra_ignore(
            HotAisleConfig,
            {
                **json.loads(record.config),
                "creds": validate_json_extra_ignore(HotAisleCreds, record.auth),
            },
        )

    def _validate_creds(self, creds: AnyHotAisleCreds, team_handle: str):
        api_client = HotAisleAPIClient(creds.api_key, team_handle)
        api_client.validate_api_key()
