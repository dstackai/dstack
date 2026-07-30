import json

from dstack._internal.core.backends.base.configurator import (
    BackendRecord,
    Configurator,
    raise_invalid_credentials_error,
)
from dstack._internal.core.backends.lambdalabs import api_client
from dstack._internal.core.backends.lambdalabs.backend import LambdaBackend
from dstack._internal.core.backends.lambdalabs.models import (
    LambdaBackendConfig,
    LambdaBackendConfigWithCreds,
    LambdaConfig,
    LambdaCreds,
    LambdaStoredConfig,
)
from dstack._internal.core.models.backends.base import (
    BackendType,
)
from dstack._internal.core.models.common import validate_extra_ignore, validate_json_extra_ignore


class LambdaConfigurator(
    Configurator[
        LambdaBackendConfig,
        LambdaBackendConfigWithCreds,
    ]
):
    TYPE = BackendType.LAMBDA
    BACKEND_CLASS = LambdaBackend

    def validate_config(self, config: LambdaBackendConfigWithCreds, default_creds_enabled: bool):
        self._validate_lambda_api_key(config.creds.api_key)

    def create_backend(
        self, project_name: str, config: LambdaBackendConfigWithCreds
    ) -> BackendRecord:
        return BackendRecord(
            config=LambdaStoredConfig(
                **validate_extra_ignore(LambdaBackendConfig, config).dict()
            ).json(),
            auth=LambdaCreds.model_validate(config.creds).json(),
        )

    def get_backend_config_with_creds(self, record: BackendRecord) -> LambdaBackendConfigWithCreds:
        config = self._get_config(record)
        return validate_extra_ignore(LambdaBackendConfigWithCreds, config)

    def get_backend_config_without_creds(self, record: BackendRecord) -> LambdaBackendConfig:
        config = self._get_config(record)
        return validate_extra_ignore(LambdaBackendConfig, config)

    def get_backend(self, record: BackendRecord) -> LambdaBackend:
        config = self._get_config(record)
        return LambdaBackend(config=config)

    def _get_config(self, record: BackendRecord) -> LambdaConfig:
        return validate_extra_ignore(
            LambdaConfig,
            {
                **json.loads(record.config),
                "creds": validate_json_extra_ignore(LambdaCreds, record.auth),
            },
        )

    def _validate_lambda_api_key(self, api_key: str):
        client = api_client.LambdaAPIClient(api_key=api_key)
        if not client.validate_api_key():
            raise_invalid_credentials_error(fields=[["creds", "api_key"]])
