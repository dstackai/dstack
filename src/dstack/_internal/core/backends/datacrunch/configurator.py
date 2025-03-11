import json

from dstack._internal.core.backends.base.configurator import (
    BackendRecord,
    Configurator,
)
from dstack._internal.core.backends.datacrunch.backend import DataCrunchBackend
from dstack._internal.core.backends.datacrunch.models import (
    AnyDataCrunchBackendConfig,
    DataCrunchBackendConfig,
    DataCrunchBackendConfigWithCreds,
    DataCrunchConfig,
    DataCrunchCreds,
    DataCrunchStoredConfig,
)
from dstack._internal.core.models.backends.base import (
    BackendType,
)

REGIONS = [
    "FIN-01",
    "ICE-01",
]

DEFAULT_REGION = "FIN-01"


class DataCrunchConfigurator(Configurator):
    TYPE = BackendType.DATACRUNCH
    BACKEND_CLASS = DataCrunchBackend

    def validate_config(
        self, config: DataCrunchBackendConfigWithCreds, default_creds_enabled: bool
    ):
        # FIXME: validate datacrunch creds
        return

    def create_backend(
        self, project_name: str, config: DataCrunchBackendConfigWithCreds
    ) -> BackendRecord:
        if config.regions is None:
            config.regions = REGIONS
        return BackendRecord(
            config=DataCrunchStoredConfig(
                **DataCrunchBackendConfig.__response__.parse_obj(config).dict()
            ).json(),
            auth=DataCrunchCreds.parse_obj(config.creds).json(),
        )

    def get_backend_config(
        self, record: BackendRecord, include_creds: bool
    ) -> AnyDataCrunchBackendConfig:
        config = self._get_config(record)
        if include_creds:
            return DataCrunchBackendConfigWithCreds.__response__.parse_obj(config)
        return DataCrunchBackendConfig.__response__.parse_obj(config)

    def get_backend(self, record: BackendRecord) -> DataCrunchBackend:
        config = self._get_config(record)
        return DataCrunchBackend(config=config)

    def _get_config(self, record: BackendRecord) -> DataCrunchConfig:
        return DataCrunchConfig.__response__(
            **json.loads(record.config),
            creds=DataCrunchCreds.parse_raw(record.auth),
        )
