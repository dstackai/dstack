from dstack._internal.core.backends.base.config import BackendConfig
from dstack._internal.core.models.backends.kubernetes import KubernetesStoredConfig


class KubernetesConfig(KubernetesStoredConfig, BackendConfig):
    pass
