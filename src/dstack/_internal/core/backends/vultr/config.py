from dstack._internal.core.backends.base.config import BackendConfig
from dstack._internal.core.backends.vultr.models import (
    AnyVultrCreds,
    VultrStoredConfig,
)


class VultrConfig(VultrStoredConfig, BackendConfig):
    creds: AnyVultrCreds
