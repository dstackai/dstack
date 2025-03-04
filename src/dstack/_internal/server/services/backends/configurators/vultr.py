import json

from dstack._internal.core.backends.base import Backend
from dstack._internal.core.backends.vultr import VultrBackend, VultrConfig, api_client
from dstack._internal.core.models.backends import (
    VultrConfigInfoWithCreds,
)
from dstack._internal.core.models.backends.base import (
    BackendType,
)
from dstack._internal.core.models.backends.vultr import (
    VultrConfigInfo,
    VultrCreds,
    VultrStoredConfig,
)
from dstack._internal.server.models import BackendModel, DecryptedString, ProjectModel
from dstack._internal.server.services.backends import Configurator
from dstack._internal.server.services.backends.configurators.base import (
    raise_invalid_credentials_error,
)

REGIONS = []


class VultrConfigurator(Configurator):
    TYPE: BackendType = BackendType.VULTR

    def validate_config(self, config: VultrConfigInfoWithCreds):
        self._validate_vultr_api_key(config.creds.api_key)

    def create_backend(
        self, project: ProjectModel, config: VultrConfigInfoWithCreds
    ) -> BackendModel:
        if config.regions is None:
            config.regions = REGIONS
        return BackendModel(
            project_id=project.id,
            type=self.TYPE.value,
            config=VultrStoredConfig(
                **VultrConfigInfo.__response__.parse_obj(config).dict()
            ).json(),
            auth=DecryptedString(plaintext=VultrCreds.parse_obj(config.creds).json()),
        )

    def get_config_info(self, model: BackendModel, include_creds: bool) -> VultrConfigInfo:
        config = self._get_backend_config(model)
        if include_creds:
            return VultrConfigInfoWithCreds.__response__.parse_obj(config)
        return VultrConfigInfo.__response__.parse_obj(config)

    def get_backend(self, model: BackendModel) -> Backend:
        config = self._get_backend_config(model)
        return VultrBackend(config=config)

    def _get_backend_config(self, model: BackendModel) -> VultrConfig:
        return VultrConfig.__response__(
            **json.loads(model.config),
            creds=VultrCreds.parse_raw(model.auth.get_plaintext_or_error()),
        )

    def _validate_vultr_api_key(self, api_key: str):
        client = api_client.VultrApiClient(api_key=api_key)
        if not client.validate_api_key():
            raise_invalid_credentials_error(fields=[["creds", "api_key"]])
