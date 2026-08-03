import json
from typing import Optional

from dstack._internal.core.backends.base.configurator import (
    BackendRecord,
    Configurator,
)
from dstack._internal.core.backends.digitalocean_base.backend import BaseDigitalOceanBackend
from dstack._internal.core.backends.digitalocean_base.models import (
    AnyBaseDigitalOceanCreds,
    BaseDigitalOceanBackendConfig,
    BaseDigitalOceanBackendConfigWithCreds,
    BaseDigitalOceanConfig,
    BaseDigitalOceanCreds,
    BaseDigitalOceanStoredConfig,
)
from dstack._internal.core.models.common import validate_extra_ignore, validate_json_extra_ignore


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
                **validate_extra_ignore(BaseDigitalOceanBackendConfig, config).model_dump()
            ).model_dump_json(),
            auth=BaseDigitalOceanCreds.model_validate(config.creds).model_dump_json(),
        )

    def get_backend_config_with_creds(
        self, record: BackendRecord
    ) -> BaseDigitalOceanBackendConfigWithCreds:
        config = self._get_config(record)
        return validate_extra_ignore(BaseDigitalOceanBackendConfigWithCreds, config)

    def get_backend_config_without_creds(
        self, record: BackendRecord
    ) -> BaseDigitalOceanBackendConfig:
        config = self._get_config(record)
        return validate_extra_ignore(BaseDigitalOceanBackendConfig, config)

    def get_backend(self, record: BackendRecord) -> BaseDigitalOceanBackend:
        raise NotImplementedError("Subclasses must implement get_backend")

    def _get_config(self, record: BackendRecord) -> BaseDigitalOceanConfig:
        return validate_extra_ignore(
            BaseDigitalOceanConfig,
            {
                **json.loads(record.config),
                "creds": validate_json_extra_ignore(BaseDigitalOceanCreds, record.auth),
            },
        )

    def _validate_creds(self, creds: AnyBaseDigitalOceanCreds, project_name: Optional[str] = None):
        pass
