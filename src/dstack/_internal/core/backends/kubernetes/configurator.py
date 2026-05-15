from dstack._internal.core.backends.base.configurator import (
    BackendRecord,
    Configurator,
    raise_invalid_credentials_error,
)
from dstack._internal.core.backends.kubernetes.backend import KubernetesBackend
from dstack._internal.core.backends.kubernetes.models import (
    KubernetesBackendConfig,
    KubernetesBackendConfigWithCreds,
    KubernetesConfig,
    KubernetesStoredConfig,
)
from dstack._internal.core.backends.kubernetes.utils import (
    check_cluster,
    get_clusters_from_backend_config,
)
from dstack._internal.core.errors import ServerClientError
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


class KubernetesConfigurator(
    Configurator[
        KubernetesBackendConfig,
        KubernetesBackendConfigWithCreds,
    ]
):
    TYPE = BackendType.KUBERNETES
    BACKEND_CLASS = KubernetesBackend

    def validate_config(
        self, config: KubernetesBackendConfigWithCreds, default_creds_enabled: bool
    ):
        self._check_config_contexts(config)
        try:
            clusters = get_clusters_from_backend_config(config, request_timeout=10, retries=0)
        except Exception as e:
            raise ServerClientError(str(e))
        for cluster in clusters:
            if not check_cluster(cluster):
                raise_invalid_credentials_error(
                    fields=[["kubeconfig"]],
                    details=f"Failed to validate cluster {cluster}",
                )

    def create_backend(
        self, project_name: str, config: KubernetesBackendConfigWithCreds
    ) -> BackendRecord:
        return BackendRecord(
            config=KubernetesStoredConfig.__response__.parse_obj(config).json(),
            auth="",
        )

    def get_backend_config_with_creds(
        self, record: BackendRecord
    ) -> KubernetesBackendConfigWithCreds:
        config = self._get_config(record)
        return KubernetesBackendConfigWithCreds.__response__.parse_obj(config)

    def get_backend_config_without_creds(self, record: BackendRecord) -> KubernetesBackendConfig:
        config = self._get_config(record)
        return KubernetesBackendConfig.__response__.parse_obj(config)

    def get_backend(self, record: BackendRecord) -> KubernetesBackend:
        return KubernetesBackend(self._get_config(record))

    def _get_config(self, record: BackendRecord) -> KubernetesConfig:
        return KubernetesConfig.__response__.parse_raw(record.config)

    def _check_config_contexts(self, config: KubernetesBackendConfig):
        if config.contexts is None:
            return
        if config.proxy_jump is not None:
            raise ServerClientError("proxy_jump must not be set if contexts is set")
        if config.namespace is not None:
            raise ServerClientError("namespace must not be set if contexts is set")
        seen: set[str] = set()
        duplicates: set[str] = set()
        for context in config.contexts:
            if isinstance(context, str):
                name = context
            else:
                name = context.name
            if name in seen:
                duplicates.add(name)
            else:
                seen.add(name)
        if duplicates:
            raise ServerClientError(f"duplicate contexts: {', '.join(sorted(duplicates))}")
