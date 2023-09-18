from dstack._internal.core.backends.base.config import BackendConfig
from dstack._internal.core.models.backends import AWSConfigInfoWithCreds


class AWSConfig(BackendConfig, AWSConfigInfoWithCreds):
    pass
