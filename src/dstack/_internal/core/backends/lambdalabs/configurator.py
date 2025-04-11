import json

from dstack._internal.core.backends.base.configurator import (
    BackendRecord,
    Configurator,
    raise_invalid_credentials_error,
)
from dstack._internal.core.backends.lambdalabs import api_client
from dstack._internal.core.backends.lambdalabs.backend import LambdaBackend
from dstack._internal.core.backends.lambdalabs.models import (
    AnyLambdaBackendConfig,
    LambdaBackendConfig,
    LambdaBackendConfigWithCreds,
    LambdaConfig,
    LambdaCreds,
    LambdaStoredConfig,
)
from dstack._internal.core.models.backends.base import (
    BackendType,
)


class LambdaConfigurator(Configurator):
    TYPE = BackendType.LAMBDA
    BACKEND_CLASS = LambdaBackend

    def validate_config(self, config: LambdaBackendConfigWithCreds, default_creds_enabled: bool):
        self._validate_lambda_api_key(config.creds.api_key)

    def create_backend(
        self, project_name: str, config: LambdaBackendConfigWithCreds
    ) -> BackendRecord:
        return BackendRecord(
            config=LambdaStoredConfig(
                **LambdaBackendConfig.__response__.parse_obj(config).dict()
            ).json(),
            auth=LambdaCreds.parse_obj(config.creds).json(),
        )

    def get_backend_config(
        self, record: BackendRecord, include_creds: bool
    ) -> AnyLambdaBackendConfig:
        config = self._get_config(record)
        if include_creds:
            return LambdaBackendConfigWithCreds.__response__.parse_obj(config)
        return LambdaBackendConfig.__response__.parse_obj(config)

    def get_backend(self, record: BackendRecord) -> LambdaBackend:
        config = self._get_config(record)
        return LambdaBackend(config=config)

    def _get_config(self, record: BackendRecord) -> LambdaConfig:
        return LambdaConfig.__response__(
            **json.loads(record.config),
            creds=LambdaCreds.parse_raw(record.auth),
        )

    def _validate_lambda_api_key(self, api_key: str):
        client = api_client.LambdaAPIClient(api_key=api_key)
        if not client.validate_api_key():
            raise_invalid_credentials_error(fields=[["creds", "api_key"]])
