import json

from datacrunch import DataCrunchClient
from datacrunch.exceptions import APIException

from dstack._internal.core.backends.base.configurator import (
    BackendRecord,
    Configurator,
    raise_invalid_credentials_error,
)
from dstack._internal.core.backends.datacrunch.backend import DataCrunchBackend
from dstack._internal.core.backends.datacrunch.models import (
    DataCrunchBackendConfig,
    DataCrunchBackendConfigWithCreds,
    DataCrunchConfig,
    DataCrunchCreds,
    DataCrunchStoredConfig,
)
from dstack._internal.core.models.backends.base import (
    BackendType,
)


class DataCrunchConfigurator(
    Configurator[
        DataCrunchBackendConfig,
        DataCrunchBackendConfigWithCreds,
    ]
):
    TYPE = BackendType.DATACRUNCH
    BACKEND_CLASS = DataCrunchBackend

    def validate_config(
        self, config: DataCrunchBackendConfigWithCreds, default_creds_enabled: bool
    ):
        self._validate_creds(config.creds)

    def create_backend(
        self, project_name: str, config: DataCrunchBackendConfigWithCreds
    ) -> BackendRecord:
        return BackendRecord(
            config=DataCrunchStoredConfig(
                **DataCrunchBackendConfig.__response__.parse_obj(config).dict()
            ).json(),
            auth=DataCrunchCreds.parse_obj(config.creds).json(),
        )

    def get_backend_config_with_creds(
        self, record: BackendRecord
    ) -> DataCrunchBackendConfigWithCreds:
        config = self._get_config(record)
        return DataCrunchBackendConfigWithCreds.__response__.parse_obj(config)

    def get_backend_config_without_creds(self, record: BackendRecord) -> DataCrunchBackendConfig:
        config = self._get_config(record)
        return DataCrunchBackendConfig.__response__.parse_obj(config)

    def get_backend(self, record: BackendRecord) -> DataCrunchBackend:
        config = self._get_config(record)
        return DataCrunchBackend(config=config)

    def _get_config(self, record: BackendRecord) -> DataCrunchConfig:
        return DataCrunchConfig.__response__(
            **json.loads(record.config),
            creds=DataCrunchCreds.parse_raw(record.auth),
        )

    def _validate_creds(self, creds: DataCrunchCreds):
        try:
            DataCrunchClient(
                client_id=creds.client_id,
                client_secret=creds.client_secret,
            )
        except APIException as e:
            if e.code == "unauthorized_request":
                raise_invalid_credentials_error(fields=[["creds", "api_key"]])
            raise
