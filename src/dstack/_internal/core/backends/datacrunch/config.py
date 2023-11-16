from dstack._internal.core.backends.base.config import BackendConfig
from dstack._internal.core.models.backends.datacrunch import (
    AnyDataCrunchCreds,
    DataCrunchStoredConfig,
)


class DataCrunchConfig(DataCrunchStoredConfig, BackendConfig):
    creds: AnyDataCrunchCreds
