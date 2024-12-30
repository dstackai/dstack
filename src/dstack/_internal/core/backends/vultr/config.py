from dstack._internal.core.backends.base.config import BackendConfig
from dstack._internal.core.models.backends.vultr import (
    AnyVultrCreds,
    VultrStoredConfig,
)


class VultrConfig(VultrStoredConfig, BackendConfig):
    creds: AnyVultrCreds
