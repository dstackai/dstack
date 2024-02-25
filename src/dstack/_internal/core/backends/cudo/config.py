from dstack._internal.core.backends.base.config import BackendConfig
from dstack._internal.core.models.backends.cudo import (
    AnyCudoCreds,
    CudoStoredConfig,
)


class CudoConfig(CudoStoredConfig, BackendConfig):
    creds: AnyCudoCreds
