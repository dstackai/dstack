from dstack._internal.core.backends.base import Backend
from dstack._internal.core.backends.gcp import GCPBackend
from dstack._internal.core.backends.gcp.config import GCPConfig
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.backends.gcp import (
    AnyGCPConfigInfo,
    GCPConfigInfo,
    GCPConfigInfoWithCreds,
    GCPConfigInfoWithCredsPartial,
    GCPConfigValues,
    GCPCreds,
)
from dstack._internal.server.models import BackendModel, ProjectModel
from dstack._internal.server.services.backends.configurators.base import Configurator


class GCPConfigurator(Configurator):
    TYPE: BackendType = BackendType.GCP

    def get_config_values(self, config: GCPConfigInfoWithCredsPartial) -> GCPConfigValues:
        pass

    def create_backend(
        self, project: ProjectModel, config: GCPConfigInfoWithCreds
    ) -> BackendModel:
        return BackendModel(
            project_id=project.id,
            type=self.TYPE.value,
            config=GCPConfigInfo.parse_obj(config).json(),
            auth=GCPCreds.parse_obj(config.creds).__root__.json(),
        )

    def get_config_info(self, model: BackendModel, include_creds: bool) -> AnyGCPConfigInfo:
        config = GCPConfigInfo.parse_raw(model.config)
        creds = GCPCreds.parse_raw(model.auth).__root__
        if include_creds:
            return GCPConfigInfoWithCreds(
                regions=config.regions,
                creds=creds,
            )
        return config

    def get_backend(self, model: BackendModel) -> GCPBackend:
        config_info = self.get_config_info(model=model, include_creds=True)
        config = GCPConfig.parse_obj(config_info)
        return GCPBackend(config=config)
