import json

from dstack._internal.core.backends.base.configurator import (
    BackendRecord,
    Configurator,
    raise_invalid_credentials_error,
)
from dstack._internal.core.backends.hotaisle.api_client import HotaisleAPIClient
from dstack._internal.core.backends.hotaisle.backend import HotaisleBackend
from dstack._internal.core.backends.hotaisle.models import (
    AnyHotaisleBackendConfig,
    AnyHotaisleCreds,
    HotaisleBackendConfig,
    HotaisleBackendConfigWithCreds,
    HotaisleConfig,
    HotaisleCreds,
    HotaisleStoredConfig,
)
from dstack._internal.core.models.backends.base import (
    BackendType,
)


class HotaisleConfigurator(Configurator):
    TYPE = BackendType.HOTAISLE
    BACKEND_CLASS = HotaisleBackend

    def validate_config(self, config: HotaisleBackendConfigWithCreds, default_creds_enabled: bool):
        self._validate_creds(config.creds, config.team_handle)

    def create_backend(
        self, project_name: str, config: HotaisleBackendConfigWithCreds
    ) -> BackendRecord:
        return BackendRecord(
            config=HotaisleStoredConfig(
                **HotaisleBackendConfig.__response__.parse_obj(config).dict()
            ).json(),
            auth=HotaisleCreds.parse_obj(config.creds).json(),
        )

    def get_backend_config(
        self, record: BackendRecord, include_creds: bool
    ) -> AnyHotaisleBackendConfig:
        config = self._get_config(record)
        if include_creds:
            return HotaisleBackendConfigWithCreds.__response__.parse_obj(config)
        return HotaisleBackendConfig.__response__.parse_obj(config)

    def get_backend(self, record: BackendRecord) -> HotaisleBackend:
        config = self._get_config(record)
        return HotaisleBackend(config=config)

    def _get_config(self, record: BackendRecord) -> HotaisleConfig:
        return HotaisleConfig.__response__(
            **json.loads(record.config),
            creds=HotaisleCreds.parse_raw(record.auth),
        )

    def _validate_creds(self, creds: AnyHotaisleCreds, team_handle: str):
        api_client = HotaisleAPIClient(creds.api_key, team_handle)
        if not api_client.validate_api_key():
            raise_invalid_credentials_error(fields=[["creds", "api_key"]])
