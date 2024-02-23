from dstack._internal.core.backends.base.config import BackendConfig
from dstack._internal.core.models.backends.cudocompute import (
    AnyCudoComputeCreds,
    CudoComputeStoredConfig,
)


class CudoComputeConfig(CudoComputeStoredConfig, BackendConfig):
    creds: AnyCudoComputeCreds
