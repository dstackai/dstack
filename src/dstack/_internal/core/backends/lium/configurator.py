import json

from dstack._internal.core.backends.base.configurator import BackendRecord, Configurator
from dstack._internal.core.backends.lium.api_client import LiumAPIClient, LiumAPIError
from dstack._internal.core.backends.lium.backend import LiumBackend
from dstack._internal.core.backends.lium.models import (
    LiumBackendConfig,
    LiumBackendConfigWithCreds,
    LiumConfig,
    LiumCreds,
    LiumStoredConfig,
)
from dstack._internal.core.errors import BackendInvalidCredentialsError
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.common import validate_extra_ignore, validate_json_extra_ignore


class LiumConfigurator(Configurator[LiumBackendConfig, LiumBackendConfigWithCreds]):
    TYPE = BackendType.LIUM
    BACKEND_CLASS = LiumBackend

    def validate_config(self, config: LiumBackendConfigWithCreds, default_creds_enabled: bool):
        try:
            LiumAPIClient(config.creds.api_key).get_user()
        except LiumAPIError as e:
            if e.status_code == 401:
                raise BackendInvalidCredentialsError(fields=[["creds", "api_key"]]) from e
            raise

    def create_backend(
        self, project_name: str, config: LiumBackendConfigWithCreds
    ) -> BackendRecord:
        return BackendRecord(
            config=LiumStoredConfig(
                **validate_extra_ignore(LiumBackendConfig, config).model_dump()
            ).model_dump_json(),
            auth=LiumCreds.model_validate(config.creds).model_dump_json(),
        )

    def get_backend_config_with_creds(self, record: BackendRecord) -> LiumBackendConfigWithCreds:
        return validate_extra_ignore(LiumBackendConfigWithCreds, self._get_config(record))

    def get_backend_config_without_creds(self, record: BackendRecord) -> LiumBackendConfig:
        return validate_extra_ignore(LiumBackendConfig, self._get_config(record))

    def get_backend(self, record: BackendRecord) -> LiumBackend:
        return LiumBackend(config=self._get_config(record))

    def _get_config(self, record: BackendRecord) -> LiumConfig:
        return validate_extra_ignore(
            LiumConfig,
            {
                **json.loads(record.config),
                "creds": validate_json_extra_ignore(LiumCreds, record.auth),
            },
        )
