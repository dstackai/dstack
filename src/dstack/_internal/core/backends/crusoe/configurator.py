import json

from dstack._internal.core.backends.base.configurator import (
    BackendRecord,
    Configurator,
    raise_invalid_credentials_error,
)
from dstack._internal.core.backends.crusoe.backend import CrusoeBackend
from dstack._internal.core.backends.crusoe.models import (
    CrusoeBackendConfig,
    CrusoeBackendConfigWithCreds,
    CrusoeConfig,
    CrusoeCreds,
    CrusoeStoredConfig,
)
from dstack._internal.core.backends.crusoe.resources import CrusoeClient
from dstack._internal.core.models.backends.base import BackendType

KNOWN_LOCATIONS = {"us-east1-a", "us-southcentral1-a", "eu-iceland1-a", "us-west1-a"}


class CrusoeConfigurator(
    Configurator[
        CrusoeBackendConfig,
        CrusoeBackendConfigWithCreds,
    ]
):
    TYPE = BackendType.CRUSOE
    BACKEND_CLASS = CrusoeBackend

    def validate_config(self, config: CrusoeBackendConfigWithCreds, default_creds_enabled: bool):
        try:
            client = CrusoeClient(config.creds, config.project_id)
            client.list_quotas()
        except Exception as e:
            raise_invalid_credentials_error(
                fields=[["creds"]],
                details=str(e),
            )
        if config.regions:
            invalid = set(config.regions) - KNOWN_LOCATIONS
            if invalid:
                raise_invalid_credentials_error(
                    fields=[["regions"]],
                    details=(
                        f"Unknown regions: {sorted(invalid)}."
                        f" Valid regions: {sorted(KNOWN_LOCATIONS)}"
                    ),
                )

    def create_backend(
        self, project_name: str, config: CrusoeBackendConfigWithCreds
    ) -> BackendRecord:
        return BackendRecord(
            config=CrusoeStoredConfig(
                **CrusoeBackendConfig.__response__.parse_obj(config).dict()
            ).json(),
            auth=CrusoeCreds.parse_obj(config.creds).json(),
        )

    def get_backend_config_with_creds(self, record: BackendRecord) -> CrusoeBackendConfigWithCreds:
        config = self._get_config(record)
        return CrusoeBackendConfigWithCreds.__response__.parse_obj(config)

    def get_backend_config_without_creds(self, record: BackendRecord) -> CrusoeBackendConfig:
        config = self._get_config(record)
        return CrusoeBackendConfig.__response__.parse_obj(config)

    def get_backend(self, record: BackendRecord) -> CrusoeBackend:
        config = self._get_config(record)
        return CrusoeBackend(config=config)

    def _get_config(self, record: BackendRecord) -> CrusoeConfig:
        return CrusoeConfig.__response__(
            **json.loads(record.config),
            creds=CrusoeCreds.parse_raw(record.auth),
        )
