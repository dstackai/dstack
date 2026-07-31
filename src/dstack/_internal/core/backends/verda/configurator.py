import json

from verda import VerdaClient
from verda.exceptions import APIException

from dstack._internal.core.backends.base.configurator import (
    BackendRecord,
    Configurator,
    raise_invalid_credentials_error,
)
from dstack._internal.core.backends.verda.backend import VerdaBackend
from dstack._internal.core.backends.verda.models import (
    VerdaBackendConfig,
    VerdaBackendConfigWithCreds,
    VerdaConfig,
    VerdaCreds,
    VerdaStoredConfig,
)
from dstack._internal.core.models.backends.base import (
    BackendType,
)
from dstack._internal.core.models.common import validate_extra_ignore, validate_json_extra_ignore


class VerdaConfigurator(
    Configurator[
        VerdaBackendConfig,
        VerdaBackendConfigWithCreds,
    ]
):
    TYPE = BackendType.VERDA
    BACKEND_CLASS = VerdaBackend

    def validate_config(self, config: VerdaBackendConfigWithCreds, default_creds_enabled: bool):
        self._validate_creds(config.creds)

    def create_backend(
        self, project_name: str, config: VerdaBackendConfigWithCreds
    ) -> BackendRecord:
        return BackendRecord(
            config=VerdaStoredConfig(
                **validate_extra_ignore(VerdaBackendConfig, config).model_dump()
            ).model_dump_json(),
            auth=VerdaCreds.model_validate(config.creds).model_dump_json(),
        )

    def get_backend_config_with_creds(self, record: BackendRecord) -> VerdaBackendConfigWithCreds:
        config = self._get_config(record)
        return validate_extra_ignore(VerdaBackendConfigWithCreds, config)

    def get_backend_config_without_creds(self, record: BackendRecord) -> VerdaBackendConfig:
        config = self._get_config(record)
        return validate_extra_ignore(VerdaBackendConfig, config)

    def get_backend(self, record: BackendRecord) -> VerdaBackend:
        config = self._get_config(record)
        return VerdaBackend(config=config)

    def _get_config(self, record: BackendRecord) -> VerdaConfig:
        return validate_extra_ignore(
            VerdaConfig,
            {
                **json.loads(record.config),
                "creds": validate_json_extra_ignore(VerdaCreds, record.auth),
            },
        )

    def _validate_creds(self, creds: VerdaCreds):
        try:
            VerdaClient(
                client_id=creds.client_id,
                client_secret=creds.client_secret,
            )
        except APIException as e:
            if e.code == "unauthorized_request":
                raise_invalid_credentials_error(fields=[["creds", "api_key"]])
            raise
