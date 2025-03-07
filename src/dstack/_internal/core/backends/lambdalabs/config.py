from dstack._internal.core.backends.base.config import BackendConfig
from dstack._internal.core.backends.lambdalabs.models import (
    AnyLambdaCreds,
    LambdaStoredConfig,
)


class LambdaConfig(LambdaStoredConfig, BackendConfig):
    creds: AnyLambdaCreds
