from dstack._internal.core.backends.azure import AzureBackend
from dstack._internal.core.backends.azure.config import AzureConfig
from dstack._internal.core.models.backends.azure import (
    AnyAzureConfigInfo,
    AzureConfigInfo,
    AzureConfigInfoWithCreds,
    AzureConfigInfoWithCredsPartial,
    AzureConfigValues,
    AzureCreds,
)
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.server.models import BackendModel, ProjectModel
from dstack._internal.server.services.backends.configurators.base import Configurator


class AzureConfigurator(Configurator):
    TYPE: BackendType = BackendType.AZURE

    def get_config_values(self, config: AzureConfigInfoWithCredsPartial) -> AzureConfigValues:
        pass

    def create_backend(
        self, project: ProjectModel, config: AzureConfigInfoWithCreds
    ) -> BackendModel:
        return BackendModel(
            project_id=project.id,
            type=self.TYPE.value,
            config=AzureConfigInfo.parse_obj(config).json(),
            auth=AzureCreds.parse_obj(config.creds).__root__.json(),
        )

    def get_config_info(self, model: BackendModel, include_creds: bool) -> AnyAzureConfigInfo:
        config = AzureConfigInfo.parse_raw(model.config)
        creds = AzureCreds.parse_raw(model.auth).__root__
        if include_creds:
            return AzureConfigInfoWithCreds(
                regions=config.regions,
                creds=creds,
            )
        return config

    def get_backend(self, model: BackendModel) -> AzureBackend:
        config_info = self.get_config_info(model=model, include_creds=True)
        config = AzureConfig.parse_obj(config_info)
        return AzureBackend(config=config)
