import json

from dstack._internal.core.backends.base.configurator import (
    Configurator,
    StoredBackendRecord,
    raise_invalid_credentials_error,
)
from dstack._internal.core.backends.vastai import api_client
from dstack._internal.core.backends.vastai.backend import VastAIBackend
from dstack._internal.core.backends.vastai.config import VastAIConfig
from dstack._internal.core.backends.vastai.models import (
    AnyVastAIBackendConfig,
    VastAIBackendConfig,
    VastAIBackendConfigWithCreds,
    VastAICreds,
    VastAIStoredConfig,
)
from dstack._internal.core.models.backends.base import (
    BackendType,
)

# VastAI regions are dynamic, currently we don't offer any filtering
REGIONS = []


class VastAIConfigurator(Configurator):
    TYPE: BackendType = BackendType.VASTAI

    def validate_config(self, config: VastAIBackendConfigWithCreds, default_creds_enabled: bool):
        self._validate_vastai_creds(config.creds.api_key)

    def create_backend(
        self, project_name: str, config: VastAIBackendConfigWithCreds
    ) -> StoredBackendRecord:
        if config.regions is None:
            config.regions = REGIONS
        return StoredBackendRecord(
            config=VastAIStoredConfig(
                **VastAIBackendConfig.__response__.parse_obj(config).dict()
            ).json(),
            auth=VastAICreds.parse_obj(config.creds).json(),
        )

    def get_backend_config(
        self, record: StoredBackendRecord, include_creds: bool
    ) -> AnyVastAIBackendConfig:
        config = self._get_config(record)
        if include_creds:
            return VastAIBackendConfigWithCreds.__response__.parse_obj(config)
        return VastAIBackendConfig.__response__.parse_obj(config)

    def get_backend(self, record: StoredBackendRecord) -> VastAIBackend:
        config = self._get_config(record)
        return VastAIBackend(config=config)

    def _get_config(self, record: StoredBackendRecord) -> VastAIConfig:
        return VastAIConfig.__response__(
            **json.loads(record.config),
            creds=VastAICreds.parse_raw(record.auth),
        )

    def _validate_vastai_creds(self, api_key: str):
        client = api_client.VastAIAPIClient(api_key=api_key)
        if not client.auth_test():
            raise_invalid_credentials_error(fields=[["creds", "api_key"]])
