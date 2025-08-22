from dstack._internal.core.backends.base.configurator import (
    BackendRecord,
    Configurator,
    raise_invalid_credentials_error,
)
from dstack._internal.core.backends.kubernetes import utils as kubernetes_utils
from dstack._internal.core.backends.kubernetes.backend import KubernetesBackend
from dstack._internal.core.backends.kubernetes.models import (
    KubernetesBackendConfig,
    KubernetesBackendConfigWithCreds,
    KubernetesConfig,
    KubernetesStoredConfig,
)
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
        try:
            api = kubernetes_utils.get_api_from_config_data(config.kubeconfig.data)
            api.list_node()
        except Exception as e:
            logger.debug("Invalid kubeconfig: %s", str(e))
            raise_invalid_credentials_error(fields=[["kubeconfig"]])

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
