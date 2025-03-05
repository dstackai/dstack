import json

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
from dstack._internal.server.services.backends.configurators.base import (
    Configurator,
    StoredBackendRecord,
    raise_invalid_credentials_error,
)

REGIONS = []


class VultrConfigurator(Configurator):
    TYPE: BackendType = BackendType.VULTR

    def validate_config(self, config: VultrConfigInfoWithCreds, default_creds_enabled: bool):
        self._validate_vultr_api_key(config.creds.api_key)

    def create_backend(
        self, project_name: str, config: VultrConfigInfoWithCreds
    ) -> StoredBackendRecord:
        if config.regions is None:
            config.regions = REGIONS
        return StoredBackendRecord(
            config=VultrStoredConfig(
                **VultrConfigInfo.__response__.parse_obj(config).dict()
            ).json(),
            auth=VultrCreds.parse_obj(config.creds).json(),
        )

    def get_config_info(self, record: StoredBackendRecord, include_creds: bool) -> VultrConfigInfo:
        config = self._get_backend_config(record)
        if include_creds:
            return VultrConfigInfoWithCreds.__response__.parse_obj(config)
        return VultrConfigInfo.__response__.parse_obj(config)

    def get_backend(self, record: StoredBackendRecord) -> VultrBackend:
        config = self._get_backend_config(record)
        return VultrBackend(config=config)

    def _get_backend_config(self, record: StoredBackendRecord) -> VultrConfig:
        return VultrConfig.__response__(
            **json.loads(record.config),
            creds=VultrCreds.parse_raw(record.auth),
        )

    def _validate_vultr_api_key(self, api_key: str):
        client = api_client.VultrApiClient(api_key=api_key)
        if not client.validate_api_key():
            raise_invalid_credentials_error(fields=[["creds", "api_key"]])
