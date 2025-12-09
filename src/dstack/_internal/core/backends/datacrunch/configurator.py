from dstack._internal.core.backends.base.configurator import BackendRecord
from dstack._internal.core.backends.datacrunch.backend import DataCrunchBackend
from dstack._internal.core.backends.verda.configurator import (
    VerdaConfigurator,
)
from dstack._internal.core.models.backends.base import (
    BackendType,
)


class DataCrunchConfigurator(VerdaConfigurator):
    TYPE = BackendType.DATACRUNCH
    BACKEND_CLASS = DataCrunchBackend

    def get_backend(self, record: BackendRecord) -> DataCrunchBackend:
        config = self._get_config(record)
        return DataCrunchBackend(config=config)
