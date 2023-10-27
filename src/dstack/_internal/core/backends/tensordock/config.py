from dstack._internal.core.backends.base.config import BackendConfig
from dstack._internal.core.models.backends.tensordock import (
    AnyTensorDockCreds,
    TensorDockStoredConfig,
)


class TensorDockConfig(TensorDockStoredConfig, BackendConfig):
    creds: AnyTensorDockCreds
