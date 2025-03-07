from dstack._internal.core.backends.base.config import BackendConfig
from dstack._internal.core.backends.datacrunch.models import (
    AnyDataCrunchCreds,
    DataCrunchStoredConfig,
)


class DataCrunchConfig(DataCrunchStoredConfig, BackendConfig):
    creds: AnyDataCrunchCreds
