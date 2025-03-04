from dstack._internal.core.backends.kubernetes import KubernetesBackend
from dstack._internal.core.backends.kubernetes import utils as kubernetes_utils
from dstack._internal.core.backends.kubernetes.config import KubernetesConfig
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.backends.kubernetes import (
    AnyKubernetesConfigInfo,
    KubernetesConfigInfo,
    KubernetesConfigInfoWithCreds,
    KubernetesStoredConfig,
)
from dstack._internal.server.models import BackendModel, DecryptedString, ProjectModel
from dstack._internal.server.services.backends.configurators.base import (
    Configurator,
    raise_invalid_credentials_error,
)
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


class KubernetesConfigurator(Configurator):
    TYPE: BackendType = BackendType.KUBERNETES

    def validate_config(self, config: KubernetesConfigInfoWithCreds):
        try:
            api = kubernetes_utils.get_api_from_config_data(config.kubeconfig.data)
            api.list_node()
        except Exception as e:
            logger.debug("Invalid kubeconfig: %s", str(e))
            raise_invalid_credentials_error(fields=[["kubeconfig"]])

    def create_backend(
        self, project: ProjectModel, config: KubernetesConfigInfoWithCreds
    ) -> BackendModel:
        return BackendModel(
            project_id=project.id,
            type=self.TYPE.value,
            config=KubernetesStoredConfig.__response__.parse_obj(config).json(),
            auth=DecryptedString(plaintext=""),
        )

    def get_config_info(self, model: BackendModel, include_creds: bool) -> AnyKubernetesConfigInfo:
        config = self._get_backend_config(model)
        if include_creds:
            return KubernetesConfigInfoWithCreds.__response__.parse_obj(config)
        return KubernetesConfigInfo.__response__.parse_obj(config)

    def get_backend(self, model: BackendModel) -> KubernetesBackend:
        return KubernetesBackend(self._get_backend_config(model))

    def _get_backend_config(self, model: BackendModel) -> KubernetesConfig:
        return KubernetesConfig.__response__.parse_raw(model.config)
