import json

from dstack._internal.core.backends.base.configurator import (
    BackendRecord,
    Configurator,
    raise_invalid_credentials_error,
)
from dstack._internal.core.backends.cloudrift.backend import CloudRiftBackend
from dstack._internal.core.backends.cloudrift.models import (
    AnyCloudRiftBackendConfig,
    AnyCloudRiftCreds,
    CloudRiftBackendConfig,
    CloudRiftBackendConfigWithCreds,
    CloudRiftConfig,
    CloudRiftCreds,
    CloudRiftStoredConfig,
)
from dstack._internal.core.models.backends.base import (
    BackendType,
)

# TODO: Add all supported regions and default regions
REGIONS = []


class CloudRiftConfigurator(Configurator):
    TYPE = BackendType.CLOUDRIFT
    BACKEND_CLASS = CloudRiftBackend

    def validate_config(
        self, config: CloudRiftBackendConfigWithCreds, default_creds_enabled: bool
    ):
        self._validate_creds(config.creds)
        # TODO: Validate additional config parameters if any

    def create_backend(
        self, project_name: str, config: CloudRiftBackendConfigWithCreds
    ) -> BackendRecord:
        if config.regions is None:
            config.regions = REGIONS
        return BackendRecord(
            config=CloudRiftStoredConfig(
                **CloudRiftBackendConfig.__response__.parse_obj(config).dict()
            ).json(),
            auth=CloudRiftCreds.parse_obj(config.creds).json(),
        )

    def get_backend_config(
        self, record: BackendRecord, include_creds: bool
    ) -> AnyCloudRiftBackendConfig:
        config = self._get_config(record)
        if include_creds:
            return CloudRiftBackendConfigWithCreds.__response__.parse_obj(config)
        return CloudRiftBackendConfig.__response__.parse_obj(config)

    def get_backend(self, record: BackendRecord) -> CloudRiftBackend:
        config = self._get_config(record)
        return CloudRiftBackend(config=config)

    def _get_config(self, record: BackendRecord) -> CloudRiftConfig:
        return CloudRiftConfig.__response__(
            **json.loads(record.config),
            creds=CloudRiftCreds.parse_raw(record.auth),
        )

    def _validate_creds(self, creds: AnyCloudRiftCreds):
        # TODO: Implement API key or other creds validation
        # if valid:
        #     return
        raise_invalid_credentials_error(fields=[["creds", "api_key"]])
