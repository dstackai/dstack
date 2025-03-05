import json

from dstack._internal.core.backends.base.configurator import (
    Configurator,
    StoredBackendRecord,
)
from dstack._internal.core.backends.datacrunch.backend import DataCrunchBackend
from dstack._internal.core.backends.datacrunch.config import DataCrunchConfig
from dstack._internal.core.backends.datacrunch.models import (
    AnyDataCrunchBackendConfig,
    DataCrunchBackendConfig,
    DataCrunchBackendConfigWithCreds,
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
    TYPE: BackendType = BackendType.DATACRUNCH

    def validate_config(
        self, config: DataCrunchBackendConfigWithCreds, default_creds_enabled: bool
    ):
        # FIXME: validate datacrunch creds
        return

    def create_backend(
        self, project_name: str, config: DataCrunchBackendConfigWithCreds
    ) -> StoredBackendRecord:
        if config.regions is None:
            config.regions = REGIONS
        return StoredBackendRecord(
            config=DataCrunchStoredConfig(
                **DataCrunchBackendConfig.__response__.parse_obj(config).dict()
            ).json(),
            auth=DataCrunchCreds.parse_obj(config.creds).json(),
        )

    def get_backend_config(
        self, record: StoredBackendRecord, include_creds: bool
    ) -> AnyDataCrunchBackendConfig:
        config = self._get_config(record)
        if include_creds:
            return DataCrunchBackendConfigWithCreds.__response__.parse_obj(config)
        return DataCrunchBackendConfig.__response__.parse_obj(config)

    def get_backend(self, record: StoredBackendRecord) -> DataCrunchBackend:
        config = self._get_config(record)
        return DataCrunchBackend(config=config)

    def _get_config(self, record: StoredBackendRecord) -> DataCrunchConfig:
        return DataCrunchConfig.__response__(
            **json.loads(record.config),
            creds=DataCrunchCreds.parse_raw(record.auth),
        )
