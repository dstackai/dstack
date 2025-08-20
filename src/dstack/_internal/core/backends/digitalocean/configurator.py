import json

from dstack._internal.core.backends.base.configurator import (
    BackendRecord,
    Configurator,
)
from dstack._internal.core.backends.digitalocean.api_client import DigitalOceanAPIClient
from dstack._internal.core.backends.digitalocean.backend import DigitalOceanBackend
from dstack._internal.core.backends.digitalocean.models import (
    AnyDigitalOceanBackendConfig,
    AnyDigitalOceanCreds,
    DigitalOceanBackendConfig,
    DigitalOceanBackendConfigWithCreds,
    DigitalOceanConfig,
    DigitalOceanCreds,
    DigitalOceanStoredConfig,
)
from dstack._internal.core.models.backends.base import (
    BackendType,
)


class DigitalOceanConfigurator(Configurator):
    TYPE = BackendType.DIGITALOCEAN
    BACKEND_CLASS = DigitalOceanBackend

    def validate_config(
        self, config: DigitalOceanBackendConfigWithCreds, default_creds_enabled: bool
    ):
        self._validate_creds(config.creds, config.flavor or "standard")

    def create_backend(
        self, project_name: str, config: DigitalOceanBackendConfigWithCreds
    ) -> BackendRecord:
        return BackendRecord(
            config=DigitalOceanStoredConfig(
                **DigitalOceanBackendConfig.__response__.parse_obj(config).dict()
            ).json(),
            auth=DigitalOceanCreds.parse_obj(config.creds).json(),
        )

    def get_backend_config(
        self, record: BackendRecord, include_creds: bool
    ) -> AnyDigitalOceanBackendConfig:
        config = self._get_config(record)
        if include_creds:
            return DigitalOceanBackendConfigWithCreds.__response__.parse_obj(config)
        return DigitalOceanBackendConfig.__response__.parse_obj(config)

    def get_backend(self, record: BackendRecord) -> DigitalOceanBackend:
        config = self._get_config(record)
        return DigitalOceanBackend(config=config)

    def _get_config(self, record: BackendRecord) -> DigitalOceanConfig:
        return DigitalOceanConfig.__response__(
            **json.loads(record.config),
            creds=DigitalOceanCreds.parse_raw(record.auth),
        )

    def _validate_creds(self, creds: AnyDigitalOceanCreds, flavor: str):
        api_client = DigitalOceanAPIClient(creds.api_key, flavor)
        api_client.validate_api_key()
