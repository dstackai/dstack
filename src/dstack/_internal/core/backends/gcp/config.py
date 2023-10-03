from dstack._internal.core.backends.base.config import BackendConfig
from dstack._internal.core.models.backends.gcp import AnyGCPCreds, GCPStoredConfig


class GCPConfig(GCPStoredConfig, BackendConfig):
    creds: AnyGCPCreds
