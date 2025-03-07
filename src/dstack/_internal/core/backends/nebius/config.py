from dstack._internal.core.backends.base.config import BackendConfig
from dstack._internal.core.backends.nebius.models import AnyNebiusCreds, NebiusStoredConfig


class NebiusConfig(NebiusStoredConfig, BackendConfig):
    creds: AnyNebiusCreds
