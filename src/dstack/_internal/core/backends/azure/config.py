from dstack._internal.core.backends.base.config import BackendConfig
from dstack._internal.core.models.backends.azure import AzureConfigInfoWithCreds


class AzureConfig(BackendConfig, AzureConfigInfoWithCreds):
    pass
