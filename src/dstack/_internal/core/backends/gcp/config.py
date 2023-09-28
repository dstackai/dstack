from dstack._internal.core.backends.base.config import BackendConfig
from dstack._internal.core.models.backends.gcp import GCPConfigInfoWithCreds


class GCPConfig(GCPConfigInfoWithCreds, BackendConfig):
    pass
