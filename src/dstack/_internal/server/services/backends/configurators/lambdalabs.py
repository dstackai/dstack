from dstack._internal.core.backends.base import Backend
from dstack._internal.core.backends.lambdalabs import LambdaBackend
from dstack._internal.core.backends.lambdalabs.config import LambdaConfig
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.backends.lambdalabs import (
    AnyLambdaConfigInfo,
    LambdaConfigInfo,
    LambdaConfigInfoWithCreds,
    LambdaConfigInfoWithCredsPartial,
    LambdaConfigValues,
    LambdaCreds,
)
from dstack._internal.server.models import BackendModel, ProjectModel
from dstack._internal.server.services.backends.configurators.base import Configurator


class LambdaConfigurator(Configurator):
    TYPE: BackendType = BackendType.LAMBDA

    def get_config_values(self, config: LambdaConfigInfoWithCredsPartial) -> LambdaConfigValues:
        pass

    def create_backend(
        self, project: ProjectModel, config: LambdaConfigInfoWithCreds
    ) -> BackendModel:
        return BackendModel(
            project_id=project.id,
            type=self.TYPE.value,
            config=LambdaConfigInfo.parse_obj(config).json(),
            auth=LambdaCreds.parse_obj(config.creds).__root__.json(),
        )

    def get_config_info(self, model: BackendModel, include_creds: bool) -> AnyLambdaConfigInfo:
        config = LambdaConfigInfo.parse_raw(model.config)
        creds = LambdaCreds.parse_raw(model.auth).__root__
        if include_creds:
            return LambdaConfigInfoWithCreds(
                regions=config.regions,
                creds=creds,
            )
        return config

    def get_backend(self, model: BackendModel) -> LambdaBackend:
        config_info = self.get_config_info(model=model, include_creds=True)
        config = LambdaConfig.parse_obj(config_info)
        return LambdaBackend(config=config)
