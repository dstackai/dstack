import json

from dstack._internal.core.backends.base.configurator import (
    BackendRecord,
    Configurator,
    raise_invalid_credentials_error,
)
from dstack._internal.core.backends.models import (
    VultrBackendConfigWithCreds,
)
from dstack._internal.core.backends.vultr import api_client
from dstack._internal.core.backends.vultr.backend import VultrBackend
from dstack._internal.core.backends.vultr.models import (
    VultrBackendConfig,
    VultrConfig,
    VultrCreds,
    VultrStoredConfig,
)
from dstack._internal.core.models.backends.base import (
    BackendType,
)

REGIONS = []


class VultrConfigurator(Configurator):
    TYPE = BackendType.VULTR
    BACKEND_CLASS = VultrBackend

    def validate_config(self, config: VultrBackendConfigWithCreds, default_creds_enabled: bool):
        self._validate_vultr_api_key(config.creds.api_key)

    def create_backend(
        self, project_name: str, config: VultrBackendConfigWithCreds
    ) -> BackendRecord:
        if config.regions is None:
            config.regions = REGIONS
        return BackendRecord(
            config=VultrStoredConfig(
                **VultrBackendConfig.__response__.parse_obj(config).dict()
            ).json(),
            auth=VultrCreds.parse_obj(config.creds).json(),
        )

    def get_backend_config(self, record: BackendRecord, include_creds: bool) -> VultrBackendConfig:
        config = self._get_config(record)
        if include_creds:
            return VultrBackendConfigWithCreds.__response__.parse_obj(config)
        return VultrBackendConfig.__response__.parse_obj(config)

    def get_backend(self, record: BackendRecord) -> VultrBackend:
        config = self._get_config(record)
        return VultrBackend(config=config)

    def _get_config(self, record: BackendRecord) -> VultrConfig:
        return VultrConfig.__response__(
            **json.loads(record.config),
            creds=VultrCreds.parse_raw(record.auth),
        )

    def _validate_vultr_api_key(self, api_key: str):
        client = api_client.VultrApiClient(api_key=api_key)
        if not client.validate_api_key():
            raise_invalid_credentials_error(fields=[["creds", "api_key"]])
