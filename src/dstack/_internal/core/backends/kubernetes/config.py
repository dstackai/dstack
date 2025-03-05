from dstack._internal.core.backends.base.config import BackendConfig
from dstack._internal.core.backends.kubernetes.models import KubernetesStoredConfig


class KubernetesConfig(KubernetesStoredConfig, BackendConfig):
    pass
