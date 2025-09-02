import json
from typing import Optional

from dstack._internal.core.backends.base.configurator import (
    BackendRecord,
    Configurator,
)
from dstack._internal.core.backends.digitalocean_base.backend import BaseDigitalOceanBackend
from dstack._internal.core.backends.digitalocean_base.models import (
    AnyBaseDigitalOceanBackendConfig,
    AnyBaseDigitalOceanCreds,
    BaseDigitalOceanBackendConfig,
    BaseDigitalOceanBackendConfigWithCreds,
    BaseDigitalOceanConfig,
    BaseDigitalOceanCreds,
    BaseDigitalOceanStoredConfig,
)


class BaseDigitalOceanConfigurator(Configurator):
    def validate_config(
        self, config: BaseDigitalOceanBackendConfigWithCreds, default_creds_enabled: bool
    ):
        self._validate_creds(config.creds, config.project_name)

    def create_backend(
        self, project_name: str, config: BaseDigitalOceanBackendConfigWithCreds
    ) -> BackendRecord:
        return BackendRecord(
            config=BaseDigitalOceanStoredConfig(
                **BaseDigitalOceanBackendConfig.__response__.parse_obj(config).dict()
            ).json(),
            auth=BaseDigitalOceanCreds.parse_obj(config.creds).json(),
        )

    def get_backend_config(
        self, record: BackendRecord, include_creds: bool
    ) -> AnyBaseDigitalOceanBackendConfig:
        config = self._get_config(record)
        if include_creds:
            return BaseDigitalOceanBackendConfigWithCreds.__response__.parse_obj(config)
        return BaseDigitalOceanBackendConfig.__response__.parse_obj(config)

    def get_backend(self, record: BackendRecord) -> BaseDigitalOceanBackend:
        pass

    def _get_config(self, record: BackendRecord) -> BaseDigitalOceanConfig:
        return BaseDigitalOceanConfig.__response__(
            **json.loads(record.config),
            creds=BaseDigitalOceanCreds.parse_raw(record.auth),
        )

    def _validate_creds(self, creds: AnyBaseDigitalOceanCreds, project_name: Optional[str] = None):
        pass
