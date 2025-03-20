import json

from dstack._internal.core.backends.base.configurator import (
    BackendRecord,
    Configurator,
    raise_invalid_credentials_error,
)
from dstack._internal.core.backends.tensordock import api_client
from dstack._internal.core.backends.tensordock.backend import TensorDockBackend
from dstack._internal.core.backends.tensordock.models import (
    AnyTensorDockBackendConfig,
    TensorDockBackendConfig,
    TensorDockBackendConfigWithCreds,
    TensorDockConfig,
    TensorDockCreds,
    TensorDockStoredConfig,
)
from dstack._internal.core.models.backends.base import (
    BackendType,
)

# TensorDock regions are dynamic, currently we don't offer any filtering
REGIONS = []


class TensorDockConfigurator(Configurator):
    TYPE = BackendType.TENSORDOCK
    BACKEND_CLASS = TensorDockBackend

    def validate_config(
        self, config: TensorDockBackendConfigWithCreds, default_creds_enabled: bool
    ):
        self._validate_tensordock_creds(config.creds.api_key, config.creds.api_token)

    def create_backend(
        self, project_name: str, config: TensorDockBackendConfigWithCreds
    ) -> BackendRecord:
        if config.regions is None:
            config.regions = REGIONS
        return BackendRecord(
            config=TensorDockStoredConfig(
                **TensorDockBackendConfig.__response__.parse_obj(config).dict()
            ).json(),
            auth=TensorDockCreds.parse_obj(config.creds).json(),
        )

    def get_backend_config(
        self, record: BackendRecord, include_creds: bool
    ) -> AnyTensorDockBackendConfig:
        config = self._get_config(record)
        if include_creds:
            return TensorDockBackendConfigWithCreds.__response__.parse_obj(config)
        return TensorDockBackendConfig.__response__.parse_obj(config)

    def get_backend(self, record: BackendRecord) -> TensorDockBackend:
        config = self._get_config(record)
        return TensorDockBackend(config=config)

    def _get_config(self, record: BackendRecord) -> TensorDockConfig:
        return TensorDockConfig.__response__(
            **json.loads(record.config),
            creds=TensorDockCreds.parse_raw(record.auth),
        )

    def _validate_tensordock_creds(self, api_key: str, api_token: str):
        client = api_client.TensorDockAPIClient(api_key=api_key, api_token=api_token)
        if not client.auth_test():
            raise_invalid_credentials_error(fields=[["creds", "api_key"], ["creds", "api_token"]])
