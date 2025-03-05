from dstack._internal.core.backends.base.config import BackendConfig
from dstack._internal.core.backends.cudo.models import (
    AnyCudoCreds,
    CudoStoredConfig,
)


class CudoConfig(CudoStoredConfig, BackendConfig):
    creds: AnyCudoCreds
