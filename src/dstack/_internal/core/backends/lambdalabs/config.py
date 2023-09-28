from dstack._internal.core.backends.base.config import BackendConfig
from dstack._internal.core.models.backends.lambdalabs import LambdaConfigInfoWithCreds


class LambdaConfig(BackendConfig, LambdaConfigInfoWithCreds):
    pass
