import json

from gpuhunt.providers.jarvislabs import JARVISLABS_REGION_URLS

from dstack._internal.core.backends.base.configurator import (
    BackendRecord,
    Configurator,
    raise_invalid_credentials_error,
)
from dstack._internal.core.backends.jarvislabs import api_client
from dstack._internal.core.backends.jarvislabs.backend import JarvisLabsBackend
from dstack._internal.core.backends.jarvislabs.models import (
    JarvisLabsBackendConfig,
    JarvisLabsBackendConfigWithCreds,
    JarvisLabsConfig,
    JarvisLabsCreds,
    JarvisLabsStoredConfig,
)
from dstack._internal.core.errors import ServerClientError
from dstack._internal.core.models.backends.base import BackendType


class JarvisLabsConfigurator(
    Configurator[
        JarvisLabsBackendConfig,
        JarvisLabsBackendConfigWithCreds,
    ]
):
    TYPE = BackendType.JARVISLABS
    BACKEND_CLASS = JarvisLabsBackend

    def validate_config(
        self, config: JarvisLabsBackendConfigWithCreds, default_creds_enabled: bool
    ):
        self._validate_api_key(config.creds.api_key)
        self._validate_regions(config.regions)

    def create_backend(
        self, project_name: str, config: JarvisLabsBackendConfigWithCreds
    ) -> BackendRecord:
        return BackendRecord(
            config=JarvisLabsStoredConfig(
                **JarvisLabsBackendConfig.__response__.parse_obj(config).dict()
            ).json(),
            auth=JarvisLabsCreds.parse_obj(config.creds).json(),
        )

    def get_backend_config_with_creds(
        self, record: BackendRecord
    ) -> JarvisLabsBackendConfigWithCreds:
        config = self._get_config(record)
        return JarvisLabsBackendConfigWithCreds.__response__.parse_obj(config)

    def get_backend_config_without_creds(self, record: BackendRecord) -> JarvisLabsBackendConfig:
        config = self._get_config(record)
        return JarvisLabsBackendConfig.__response__.parse_obj(config)

    def get_backend(self, record: BackendRecord) -> JarvisLabsBackend:
        config = self._get_config(record)
        return JarvisLabsBackend(config=config)

    def _get_config(self, record: BackendRecord) -> JarvisLabsConfig:
        return JarvisLabsConfig.__response__(
            **json.loads(record.config),
            creds=JarvisLabsCreds.parse_raw(record.auth),
        )

    def _validate_api_key(self, api_key: str):
        client = api_client.JarvisLabsAPIClient(api_key=api_key)
        if not client.validate_api_key():
            raise_invalid_credentials_error(fields=[["creds", "api_key"]])

    def _validate_regions(self, regions: list[str] | None):
        if not regions:
            return
        invalid_regions = sorted(set(regions) - set(JARVISLABS_REGION_URLS))
        if invalid_regions:
            raise ServerClientError(
                msg=(
                    f"Unsupported JarvisLabs regions: {invalid_regions}. "
                    f"Supported regions: {sorted(JARVISLABS_REGION_URLS)}. "
                    "JarvisLabs does not expose provisioning endpoint discovery."
                ),
                fields=[["regions"]],
            )
