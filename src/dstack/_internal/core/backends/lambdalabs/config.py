from dstack._internal.core.backends.base.config import BackendConfig
from dstack._internal.core.models.backends.lambdalabs import (
    AnyLambdaCreds,
    LambdaConfigInfoWithCreds,
    LambdaStoredConfig,
)


class LambdaConfig(LambdaStoredConfig, BackendConfig):
    creds: AnyLambdaCreds
