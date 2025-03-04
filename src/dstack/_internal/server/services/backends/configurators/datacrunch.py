import json

from dstack._internal.core.backends.datacrunch import DataCrunchBackend
from dstack._internal.core.backends.datacrunch.config import DataCrunchConfig
from dstack._internal.core.models.backends.base import (
    BackendType,
)
from dstack._internal.core.models.backends.datacrunch import (
    AnyDataCrunchConfigInfo,
    DataCrunchConfigInfo,
    DataCrunchConfigInfoWithCreds,
    DataCrunchCreds,
    DataCrunchStoredConfig,
)
from dstack._internal.server.models import BackendModel, DecryptedString, ProjectModel
from dstack._internal.server.services.backends.configurators.base import Configurator

REGIONS = [
    "FIN-01",
    "ICE-01",
]

DEFAULT_REGION = "FIN-01"


class DataCrunchConfigurator(Configurator):
    TYPE: BackendType = BackendType.DATACRUNCH

    def validate_config(self, config: DataCrunchConfigInfoWithCreds):
        # FIXME: validate datacrunch creds
        return

    def create_backend(
        self, project: ProjectModel, config: DataCrunchConfigInfoWithCreds
    ) -> BackendModel:
        if config.regions is None:
            config.regions = REGIONS
        return BackendModel(
            project_id=project.id,
            type=self.TYPE.value,
            config=DataCrunchStoredConfig(
                **DataCrunchConfigInfo.__response__.parse_obj(config).dict()
            ).json(),
            auth=DecryptedString(plaintext=DataCrunchCreds.parse_obj(config.creds).json()),
        )

    def get_config_info(self, model: BackendModel, include_creds: bool) -> AnyDataCrunchConfigInfo:
        config = self._get_backend_config(model)
        if include_creds:
            return DataCrunchConfigInfoWithCreds.__response__.parse_obj(config)
        return DataCrunchConfigInfo.__response__.parse_obj(config)

    def get_backend(self, model: BackendModel) -> DataCrunchBackend:
        config = self._get_backend_config(model)
        return DataCrunchBackend(config=config)

    def _get_backend_config(self, model: BackendModel) -> DataCrunchConfig:
        return DataCrunchConfig.__response__(
            **json.loads(model.config),
            creds=DataCrunchCreds.parse_raw(model.auth.get_plaintext_or_error()),
        )
