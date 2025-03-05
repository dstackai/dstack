import json

from dstack._internal.core.backends.base.configurator import (
    Configurator,
    StoredBackendRecord,
    raise_invalid_credentials_error,
)
from dstack._internal.core.backends.runpod import api_client
from dstack._internal.core.backends.runpod.backend import RunpodBackend, RunpodConfig
from dstack._internal.core.backends.runpod.models import (
    RunpodConfigInfo,
    RunpodConfigInfoWithCreds,
    RunpodCreds,
    RunpodStoredConfig,
)
from dstack._internal.core.models.backends.base import BackendType


class RunpodConfigurator(Configurator):
    TYPE: BackendType = BackendType.RUNPOD

    def validate_config(self, config: RunpodConfigInfoWithCreds, default_creds_enabled: bool):
        self._validate_runpod_api_key(config.creds.api_key)

    def create_backend(
        self, project_name: str, config: RunpodConfigInfoWithCreds
    ) -> StoredBackendRecord:
        return StoredBackendRecord(
            config=RunpodStoredConfig(
                **RunpodConfigInfo.__response__.parse_obj(config).dict()
            ).json(),
            auth=RunpodCreds.parse_obj(config.creds).json(),
        )

    def get_config_info(
        self, record: StoredBackendRecord, include_creds: bool
    ) -> RunpodConfigInfo:
        config = self._get_backend_config(record)
        if include_creds:
            return RunpodConfigInfoWithCreds.__response__.parse_obj(config)
        return RunpodConfigInfo.__response__.parse_obj(config)

    def get_backend(self, record: StoredBackendRecord) -> RunpodBackend:
        config = self._get_backend_config(record)
        return RunpodBackend(config=config)

    def _get_backend_config(self, record: StoredBackendRecord) -> RunpodConfig:
        return RunpodConfig(
            **json.loads(record.config),
            creds=RunpodCreds.parse_raw(record.auth),
        )

    def _validate_runpod_api_key(self, api_key: str):
        client = api_client.RunpodApiClient(api_key=api_key)
        if not client.validate_api_key():
            raise_invalid_credentials_error(fields=[["creds", "api_key"]])
