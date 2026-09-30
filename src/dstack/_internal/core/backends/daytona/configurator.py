import json

from gpuhunt.providers.daytona import GPU_REGION

from dstack._internal.core.backends.base.configurator import BackendRecord, Configurator
from dstack._internal.core.backends.daytona.api_client import DaytonaAPIClient
from dstack._internal.core.backends.daytona.backend import DaytonaBackend
from dstack._internal.core.backends.daytona.models import (
    DaytonaBackendConfig,
    DaytonaBackendConfigWithCreds,
    DaytonaConfig,
    DaytonaCreds,
    DaytonaStoredConfig,
)
from dstack._internal.core.errors import BackendInvalidCredentialsError, ServerClientError
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.common import validate_extra_ignore, validate_json_extra_ignore


class DaytonaConfigurator(Configurator[DaytonaBackendConfig, DaytonaBackendConfigWithCreds]):
    TYPE = BackendType.DAYTONA
    BACKEND_CLASS = DaytonaBackend

    def validate_config(self, config: DaytonaBackendConfigWithCreds, default_creds_enabled: bool):
        client = DaytonaAPIClient(api_key=config.creds.api_key)
        api_key = client.get_current_api_key()
        required_permissions = {"write:sandboxes", "delete:sandboxes", "read:limits"}
        missing_permissions = sorted(required_permissions - set(api_key["permissions"]))
        if missing_permissions:
            raise BackendInvalidCredentialsError(
                msg=f"Daytona API key is missing permissions: {', '.join(missing_permissions)}",
                fields=[["creds", "api_key"]],
            )
        if not config.regions:
            return
        regions = {GPU_REGION, *(region["id"] for region in client.get_shared_regions())}
        invalid_regions = sorted(set(config.regions) - regions)
        if invalid_regions:
            raise ServerClientError(
                msg=(
                    f"Unsupported Daytona regions: {invalid_regions}. "
                    f"Supported regions: {sorted(regions)}."
                ),
                fields=[["regions"]],
            )

    def create_backend(
        self, project_name: str, config: DaytonaBackendConfigWithCreds
    ) -> BackendRecord:
        return BackendRecord(
            config=DaytonaStoredConfig(
                **validate_extra_ignore(DaytonaBackendConfig, config).model_dump()
            ).model_dump_json(),
            auth=DaytonaCreds.model_validate(config.creds).model_dump_json(),
        )

    def get_backend_config_with_creds(
        self, record: BackendRecord
    ) -> DaytonaBackendConfigWithCreds:
        return validate_extra_ignore(DaytonaBackendConfigWithCreds, self._get_config(record))

    def get_backend_config_without_creds(self, record: BackendRecord) -> DaytonaBackendConfig:
        return validate_extra_ignore(DaytonaBackendConfig, self._get_config(record))

    def get_backend(self, record: BackendRecord) -> DaytonaBackend:
        return DaytonaBackend(config=self._get_config(record))

    def _get_config(self, record: BackendRecord) -> DaytonaConfig:
        return validate_extra_ignore(
            DaytonaConfig,
            {
                **json.loads(record.config),
                "creds": validate_json_extra_ignore(DaytonaCreds, record.auth),
            },
        )
