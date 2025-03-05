from dstack._internal.core.backends.base.config import BackendConfig
from dstack._internal.core.backends.tensordock.models import (
    AnyTensorDockCreds,
    TensorDockStoredConfig,
)


class TensorDockConfig(TensorDockStoredConfig, BackendConfig):
    creds: AnyTensorDockCreds
