from dstack._internal.core.backends.base.config import BackendConfig
from dstack._internal.core.models.backends.runpod import (
    AnyRunpodCreds,
    RunpodStoredConfig,
)


class RunpodConfig(RunpodStoredConfig, BackendConfig):
    creds: AnyRunpodCreds
