from dstack._internal.core.backends.base.config import BackendConfig
from dstack._internal.core.backends.runpod.models import (
    AnyRunpodCreds,
    RunpodStoredConfig,
)

RUNPOD_COMMUNITY_CLOUD_DEFAULT = True


class RunpodConfig(RunpodStoredConfig, BackendConfig):
    creds: AnyRunpodCreds

    @property
    def allow_community_cloud(self) -> bool:
        if self.community_cloud is not None:
            return self.community_cloud
        return RUNPOD_COMMUNITY_CLOUD_DEFAULT
