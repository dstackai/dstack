import json

from dstack._internal.core.backends.base.configurator import (
    BackendRecord,
    Configurator,
)
from dstack._internal.core.backends.hotaisle.api_client import HotAisleAPIClient
from dstack._internal.core.backends.hotaisle.backend import HotAisleBackend
from dstack._internal.core.backends.hotaisle.models import (
    AnyHotAisleBackendConfig,
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


class HotAisleConfigurator(Configurator):
    TYPE = BackendType.HOTAISLE
    BACKEND_CLASS = HotAisleBackend

    def validate_config(self, config: HotAisleBackendConfigWithCreds, default_creds_enabled: bool):
        self._validate_creds(config.creds, config.team_handle)

    def create_backend(
        self, project_name: str, config: HotAisleBackendConfigWithCreds
    ) -> BackendRecord:
        return BackendRecord(
            config=HotAisleStoredConfig(
                **HotAisleBackendConfig.__response__.parse_obj(config).dict()
            ).json(),
            auth=HotAisleCreds.parse_obj(config.creds).json(),
        )

    def get_backend_config(
        self, record: BackendRecord, include_creds: bool
    ) -> AnyHotAisleBackendConfig:
        config = self._get_config(record)
        if include_creds:
            return HotAisleBackendConfigWithCreds.__response__.parse_obj(config)
        return HotAisleBackendConfig.__response__.parse_obj(config)

    def get_backend(self, record: BackendRecord) -> HotAisleBackend:
        config = self._get_config(record)
        return HotAisleBackend(config=config)

    def _get_config(self, record: BackendRecord) -> HotAisleConfig:
        return HotAisleConfig.__response__(
            **json.loads(record.config),
            creds=HotAisleCreds.parse_raw(record.auth),
        )

    def _validate_creds(self, creds: AnyHotAisleCreds, team_handle: str):
        api_client = HotAisleAPIClient(creds.api_key, team_handle)
        api_client.validate_api_key()
