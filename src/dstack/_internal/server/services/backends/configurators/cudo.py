import json

from dstack._internal.core.backends.base import Backend
from dstack._internal.core.backends.cudo import CudoBackend, CudoConfig, api_client
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.backends.cudo import (
    CudoConfigInfo,
    CudoConfigInfoWithCreds,
    CudoCreds,
    CudoStoredConfig,
)
from dstack._internal.server.models import BackendModel, DecryptedString, ProjectModel
from dstack._internal.server.services.backends import Configurator
from dstack._internal.server.services.backends.configurators.base import (
    raise_invalid_credentials_error,
)

REGIONS = [
    "no-luster-1",
    "se-smedjebacken-1",
    "gb-london-1",
    "se-stockholm-1",
    "us-newyork-1",
    "us-santaclara-1",
]

DEFAULT_REGION = "no-luster-1"


class CudoConfigurator(Configurator):
    TYPE: BackendType = BackendType.CUDO

    def validate_config(self, config: CudoConfigInfoWithCreds):
        self._validate_cudo_api_key(config.creds.api_key)

    def create_backend(
        self, project: ProjectModel, config: CudoConfigInfoWithCreds
    ) -> BackendModel:
        if config.regions is None:
            config.regions = REGIONS
        return BackendModel(
            project_id=project.id,
            type=self.TYPE.value,
            config=CudoStoredConfig(**CudoConfigInfo.__response__.parse_obj(config).dict()).json(),
            auth=DecryptedString(plaintext=CudoCreds.parse_obj(config.creds).json()),
        )

    def get_config_info(self, model: BackendModel, include_creds: bool) -> CudoConfigInfo:
        config = self._get_backend_config(model)
        if include_creds:
            return CudoConfigInfoWithCreds.__response__.parse_obj(config)
        return CudoConfigInfo.__response__.parse_obj(config)

    def get_backend(self, model: BackendModel) -> Backend:
        config = self._get_backend_config(model)
        return CudoBackend(config=config)

    def _get_backend_config(self, model: BackendModel) -> CudoConfig:
        return CudoConfig.__response__(
            **json.loads(model.config),
            creds=CudoCreds.parse_raw(model.auth.get_plaintext_or_error()),
        )

    def _validate_cudo_api_key(self, api_key: str):
        client = api_client.CudoApiClient(api_key=api_key)
        if not client.validate_api_key():
            raise_invalid_credentials_error(fields=[["creds", "api_key"]])
