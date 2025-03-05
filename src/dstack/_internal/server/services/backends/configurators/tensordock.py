import json

from dstack._internal.core.backends.tensordock import TensorDockBackend, api_client
from dstack._internal.core.backends.tensordock.config import TensorDockConfig
from dstack._internal.core.models.backends.base import (
    BackendType,
)
from dstack._internal.core.models.backends.tensordock import (
    AnyTensorDockConfigInfo,
    TensorDockConfigInfo,
    TensorDockConfigInfoWithCreds,
    TensorDockCreds,
    TensorDockStoredConfig,
)
from dstack._internal.server.services.backends.configurators.base import (
    Configurator,
    StoredBackendRecord,
    raise_invalid_credentials_error,
)

# TensorDock regions are dynamic, currently we don't offer any filtering
REGIONS = []


class TensorDockConfigurator(Configurator):
    TYPE: BackendType = BackendType.TENSORDOCK

    def validate_config(self, config: TensorDockConfigInfoWithCreds):
        self._validate_tensordock_creds(config.creds.api_key, config.creds.api_token)

    def create_backend(
        self, project_name: str, config: TensorDockConfigInfoWithCreds
    ) -> StoredBackendRecord:
        if config.regions is None:
            config.regions = REGIONS
        return StoredBackendRecord(
            config=TensorDockStoredConfig(
                **TensorDockConfigInfo.__response__.parse_obj(config).dict()
            ).json(),
            auth=TensorDockCreds.parse_obj(config.creds).json(),
        )

    def get_config_info(
        self, record: StoredBackendRecord, include_creds: bool
    ) -> AnyTensorDockConfigInfo:
        config = self._get_backend_config(record)
        if include_creds:
            return TensorDockConfigInfoWithCreds.__response__.parse_obj(config)
        return TensorDockConfigInfo.__response__.parse_obj(config)

    def get_backend(self, record: StoredBackendRecord) -> TensorDockBackend:
        config = self._get_backend_config(record)
        return TensorDockBackend(config=config)

    def _get_backend_config(self, record: StoredBackendRecord) -> TensorDockConfig:
        return TensorDockConfig.__response__(
            **json.loads(record.config),
            creds=TensorDockCreds.parse_raw(record.auth),
        )

    def _validate_tensordock_creds(self, api_key: str, api_token: str):
        client = api_client.TensorDockAPIClient(api_key=api_key, api_token=api_token)
        if not client.auth_test():
            raise_invalid_credentials_error(fields=[["creds", "api_key"], ["creds", "api_token"]])
