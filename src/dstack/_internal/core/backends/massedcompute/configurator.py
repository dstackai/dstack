import json

from dstack._internal.core.backends.base.configurator import (
    BackendRecord,
    Configurator,
    raise_invalid_credentials_error,
)
from dstack._internal.core.backends.massedcompute.api_client import MassedComputeAPIClient
from dstack._internal.core.backends.massedcompute.backend import MassedComputeBackend
from dstack._internal.core.backends.massedcompute.models import (
    MassedComputeBackendConfig,
    MassedComputeBackendConfigWithCreds,
    MassedComputeConfig,
    MassedComputeCreds,
    MassedComputeStoredConfig,
)
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.common import validate_extra_ignore, validate_json_extra_ignore


class MassedComputeConfigurator(
    Configurator[MassedComputeBackendConfig, MassedComputeBackendConfigWithCreds]
):
    TYPE = BackendType.MASSEDCOMPUTE
    BACKEND_CLASS = MassedComputeBackend

    def validate_config(
        self, config: MassedComputeBackendConfigWithCreds, default_creds_enabled: bool
    ) -> None:
        if not MassedComputeAPIClient(config.creds.api_key).validate_api_key():
            raise_invalid_credentials_error(fields=[["creds", "api_key"]])

    def create_backend(
        self, project_name: str, config: MassedComputeBackendConfigWithCreds
    ) -> BackendRecord:
        return BackendRecord(
            config=MassedComputeStoredConfig(
                **validate_extra_ignore(MassedComputeBackendConfig, config).model_dump()
            ).model_dump_json(),
            auth=MassedComputeCreds.model_validate(config.creds).model_dump_json(),
        )

    def get_backend_config_with_creds(
        self, record: BackendRecord
    ) -> MassedComputeBackendConfigWithCreds:
        return validate_extra_ignore(MassedComputeBackendConfigWithCreds, self._get_config(record))

    def get_backend_config_without_creds(
        self, record: BackendRecord
    ) -> MassedComputeBackendConfig:
        return validate_extra_ignore(MassedComputeBackendConfig, self._get_config(record))

    def get_backend(self, record: BackendRecord) -> MassedComputeBackend:
        return MassedComputeBackend(config=self._get_config(record))

    def _get_config(self, record: BackendRecord) -> MassedComputeConfig:
        return validate_extra_ignore(
            MassedComputeConfig,
            {
                **json.loads(record.config),
                "creds": validate_json_extra_ignore(MassedComputeCreds, record.auth),
            },
        )
