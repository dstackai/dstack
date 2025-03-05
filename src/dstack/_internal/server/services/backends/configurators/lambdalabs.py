import json

from dstack._internal.core.backends.lambdalabs import LambdaBackend, api_client
from dstack._internal.core.backends.lambdalabs.config import LambdaConfig
from dstack._internal.core.models.backends.base import (
    BackendType,
)
from dstack._internal.core.models.backends.lambdalabs import (
    AnyLambdaConfigInfo,
    LambdaConfigInfo,
    LambdaConfigInfoWithCreds,
    LambdaCreds,
    LambdaStoredConfig,
)
from dstack._internal.server.services.backends.configurators.base import (
    Configurator,
    StoredBackendRecord,
    raise_invalid_credentials_error,
)

REGIONS = [
    "us-south-1",
    "us-south-2",
    "us-south-3",
    "us-west-2",
    "us-west-1",
    "us-midwest-1",
    "us-west-3",
    "us-east-1",
    "us-east-2",
    "europe-central-1",
    "asia-south-1",
    "me-west-1",
    "asia-northeast-1",
    "asia-northeast-2",
]

DEFAULT_REGION = "us-east-1"


class LambdaConfigurator(Configurator):
    TYPE: BackendType = BackendType.LAMBDA

    def validate_config(self, config: LambdaConfigInfoWithCreds):
        self._validate_lambda_api_key(config.creds.api_key)

    def create_backend(
        self, project_name: str, config: LambdaConfigInfoWithCreds
    ) -> StoredBackendRecord:
        if config.regions is None:
            config.regions = REGIONS
        return StoredBackendRecord(
            config=LambdaStoredConfig(
                **LambdaConfigInfo.__response__.parse_obj(config).dict()
            ).json(),
            auth=LambdaCreds.parse_obj(config.creds).json(),
        )

    def get_config_info(
        self, record: StoredBackendRecord, include_creds: bool
    ) -> AnyLambdaConfigInfo:
        config = self._get_backend_config(record)
        if include_creds:
            return LambdaConfigInfoWithCreds.__response__.parse_obj(config)
        return LambdaConfigInfo.__response__.parse_obj(config)

    def get_backend(self, record: StoredBackendRecord) -> LambdaBackend:
        config = self._get_backend_config(record)
        return LambdaBackend(config=config)

    def _get_backend_config(self, record: StoredBackendRecord) -> LambdaConfig:
        return LambdaConfig.__response__(
            **json.loads(record.config),
            creds=LambdaCreds.parse_raw(record.auth),
        )

    def _validate_lambda_api_key(self, api_key: str):
        client = api_client.LambdaAPIClient(api_key=api_key)
        if not client.validate_api_key():
            raise_invalid_credentials_error(fields=[["creds", "api_key"]])
