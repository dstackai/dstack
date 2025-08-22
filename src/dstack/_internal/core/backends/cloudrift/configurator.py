import json

from dstack._internal.core.backends.base.configurator import (
    BackendRecord,
    Configurator,
    raise_invalid_credentials_error,
)
from dstack._internal.core.backends.cloudrift.api_client import RiftClient
from dstack._internal.core.backends.cloudrift.backend import CloudRiftBackend
from dstack._internal.core.backends.cloudrift.models import (
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


class CloudRiftConfigurator(
    Configurator[
        CloudRiftBackendConfig,
        CloudRiftBackendConfigWithCreds,
    ]
):
    TYPE = BackendType.CLOUDRIFT
    BACKEND_CLASS = CloudRiftBackend

    def validate_config(
        self, config: CloudRiftBackendConfigWithCreds, default_creds_enabled: bool
    ):
        self._validate_creds(config.creds)

    def create_backend(
        self, project_name: str, config: CloudRiftBackendConfigWithCreds
    ) -> BackendRecord:
        return BackendRecord(
            config=CloudRiftStoredConfig(
                **CloudRiftBackendConfig.__response__.parse_obj(config).dict()
            ).json(),
            auth=CloudRiftCreds.parse_obj(config.creds).json(),
        )

    def get_backend_config_with_creds(
        self, record: BackendRecord
    ) -> CloudRiftBackendConfigWithCreds:
        config = self._get_config(record)
        return CloudRiftBackendConfigWithCreds.__response__.parse_obj(config)

    def get_backend_config_without_creds(self, record: BackendRecord) -> CloudRiftBackendConfig:
        config = self._get_config(record)
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
        if not isinstance(creds, CloudRiftCreds):
            raise_invalid_credentials_error(fields=[["creds"]])
        client = RiftClient(creds.api_key)
        if not client.validate_api_key():
            raise_invalid_credentials_error(fields=[["creds", "api_key"]])
