from typing import List, Optional

from dstack._internal.core.backends.kubernetes import KubernetesBackend
from dstack._internal.core.backends.kubernetes.config import KubernetesConfig
from dstack._internal.core.errors import BackendInvalidCredentialsError
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.backends.kubernetes import (
    AnyKubernetesConfigInfo,
    KubernetesConfigInfo,
    KubernetesConfigInfoWithCreds,
    KubernetesConfigInfoWithCredsPartial,
    KubernetesConfigValues,
    KubernetesStoredConfig,
)
from dstack._internal.server.models import BackendModel, ProjectModel
from dstack._internal.server.services.backends.configurators.base import Configurator


class KubernetesConfigurator(Configurator):
    TYPE: BackendType = BackendType.KUBERNETES

    def get_default_configs(self) -> List[KubernetesConfigInfoWithCreds]:
        # TODO: automatically pick up kubernetes config
        return []

    def get_config_values(
        self, config: KubernetesConfigInfoWithCredsPartial
    ) -> KubernetesConfigValues:
        # TODO: validate kubeconfig
        return KubernetesConfigValues()

    def create_backend(
        self, project: ProjectModel, config: KubernetesConfigInfoWithCreds
    ) -> BackendModel:
        return BackendModel(
            project_id=project.id,
            type=self.TYPE.value,
            config=KubernetesStoredConfig.parse_obj(config).json(),
            auth="",
        )

    def get_config_info(self, model: BackendModel, include_creds: bool) -> AnyKubernetesConfigInfo:
        config = self._get_backend_config(model)
        if include_creds:
            return KubernetesConfigInfoWithCreds.parse_obj(config)
        return KubernetesConfigInfo.parse_obj(config)

    def get_backend(self, model: BackendModel) -> KubernetesBackend:
        return KubernetesBackend(self._get_backend_config(model))

    def _get_backend_config(self, model: BackendModel) -> KubernetesConfig:
        return KubernetesConfig.parse_raw(model.config)
