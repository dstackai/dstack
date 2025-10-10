import json

from dstack._internal.core.backends.base.configurator import (
    BackendRecord,
    Configurator,
    raise_invalid_credentials_error,
)
from dstack._internal.core.backends.runpod import api_client
from dstack._internal.core.backends.runpod.backend import RunpodBackend
from dstack._internal.core.backends.runpod.models import (
    RunpodBackendConfig,
    RunpodBackendConfigWithCreds,
    RunpodConfig,
    RunpodCreds,
    RunpodStoredConfig,
)
from dstack._internal.core.models.backends.base import BackendType


class RunpodConfigurator(
    Configurator[
        RunpodBackendConfig,
        RunpodBackendConfigWithCreds,
    ]
):
    TYPE = BackendType.RUNPOD
    BACKEND_CLASS = RunpodBackend

    def validate_config(self, config: RunpodBackendConfigWithCreds, default_creds_enabled: bool):
        self._validate_runpod_api_key(config.creds.api_key)

    def create_backend(
        self, project_name: str, config: RunpodBackendConfigWithCreds
    ) -> BackendRecord:
        return BackendRecord(
            config=RunpodStoredConfig(
                **RunpodBackendConfig.__response__.parse_obj(config).dict()
            ).json(),
            auth=RunpodCreds.parse_obj(config.creds).json(),
        )

    def get_backend_config_with_creds(self, record: BackendRecord) -> RunpodBackendConfigWithCreds:
        config = self._get_config(record)
        return RunpodBackendConfigWithCreds.__response__.parse_obj(config)

    def get_backend_config_without_creds(self, record: BackendRecord) -> RunpodBackendConfig:
        config = self._get_config(record)
        return RunpodBackendConfig.__response__.parse_obj(config)

    def get_backend(self, record: BackendRecord) -> RunpodBackend:
        config = self._get_config(record)
        return RunpodBackend(config=config)

    def _get_config(self, record: BackendRecord) -> RunpodConfig:
        return RunpodConfig(
            **json.loads(record.config),
            creds=RunpodCreds.parse_raw(record.auth),
        )

    def _validate_runpod_api_key(self, api_key: str):
        client = api_client.RunpodApiClient(api_key=api_key)
        if not client.validate_api_key():
            raise_invalid_credentials_error(fields=[["creds", "api_key"]])
