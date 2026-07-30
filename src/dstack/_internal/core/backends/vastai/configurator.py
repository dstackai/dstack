import json

from dstack._internal.core.backends.base.configurator import (
    BackendRecord,
    Configurator,
    raise_invalid_credentials_error,
)
from dstack._internal.core.backends.vastai import api_client
from dstack._internal.core.backends.vastai.backend import VastAIBackend
from dstack._internal.core.backends.vastai.models import (
    VastAIBackendConfig,
    VastAIBackendConfigWithCreds,
    VastAIConfig,
    VastAICreds,
    VastAIStoredConfig,
)
from dstack._internal.core.models.backends.base import (
    BackendType,
)
from dstack._internal.core.models.common import validate_extra_ignore, validate_json_extra_ignore

REGIONS = []


class VastAIConfigurator(
    Configurator[
        VastAIBackendConfig,
        VastAIBackendConfigWithCreds,
    ]
):
    TYPE = BackendType.VASTAI
    BACKEND_CLASS = VastAIBackend

    def validate_config(self, config: VastAIBackendConfigWithCreds, default_creds_enabled: bool):
        self._validate_vastai_creds(config.creds.api_key)

    def create_backend(
        self, project_name: str, config: VastAIBackendConfigWithCreds
    ) -> BackendRecord:
        if config.regions is None:
            config.regions = REGIONS
        return BackendRecord(
            config=VastAIStoredConfig(
                **validate_extra_ignore(VastAIBackendConfig, config).dict()
            ).json(),
            auth=VastAICreds.model_validate(config.creds).json(),
        )

    def get_backend_config_with_creds(self, record: BackendRecord) -> VastAIBackendConfigWithCreds:
        config = self._get_config(record)
        return validate_extra_ignore(VastAIBackendConfigWithCreds, config)

    def get_backend_config_without_creds(self, record: BackendRecord) -> VastAIBackendConfig:
        config = self._get_config(record)
        return validate_extra_ignore(VastAIBackendConfig, config)

    def get_backend(self, record: BackendRecord) -> VastAIBackend:
        config = self._get_config(record)
        return VastAIBackend(config=config)

    def _get_config(self, record: BackendRecord) -> VastAIConfig:
        return validate_extra_ignore(
            VastAIConfig,
            {
                **json.loads(record.config),
                "creds": validate_json_extra_ignore(VastAICreds, record.auth),
            },
        )

    def _validate_vastai_creds(self, api_key: str):
        client = api_client.VastAIAPIClient(api_key=api_key)
        if not client.auth_test():
            raise_invalid_credentials_error(fields=[["creds", "api_key"]])
