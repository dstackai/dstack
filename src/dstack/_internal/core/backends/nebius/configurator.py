import json

from nebius.aio.service_error import RequestError

from dstack._internal.core.backends.base.configurator import (
    BackendRecord,
    Configurator,
    raise_invalid_credentials_error,
)
from dstack._internal.core.backends.nebius import resources
from dstack._internal.core.backends.nebius.backend import NebiusBackend
from dstack._internal.core.backends.nebius.fabrics import get_all_infiniband_fabrics
from dstack._internal.core.backends.nebius.models import (
    NebiusBackendConfig,
    NebiusBackendConfigWithCreds,
    NebiusConfig,
    NebiusCreds,
    NebiusServiceAccountCreds,
    NebiusStoredConfig,
)
from dstack._internal.core.models.backends.base import BackendType


class NebiusConfigurator(
    Configurator[
        NebiusBackendConfig,
        NebiusBackendConfigWithCreds,
    ]
):
    TYPE = BackendType.NEBIUS
    BACKEND_CLASS = NebiusBackend

    def validate_config(self, config: NebiusBackendConfigWithCreds, default_creds_enabled: bool):
        assert isinstance(config.creds, NebiusServiceAccountCreds)
        try:
            sdk = resources.make_sdk(config.creds)
            # check that it's possible to build the projects map with configured settings
            resources.get_region_to_project_id_map(
                sdk, configured_regions=config.regions, configured_project_ids=config.projects
            )
        except (ValueError, RequestError) as e:
            raise_invalid_credentials_error(
                fields=[["creds"]],
                details=str(e),
            )
        valid_fabrics = get_all_infiniband_fabrics()
        if invalid_fabrics := set(config.fabrics or []) - valid_fabrics:
            raise_invalid_credentials_error(
                fields=[["fabrics"]],
                details=(
                    "These InfiniBand fabrics do not exist or are not known to dstack:"
                    f" {sorted(invalid_fabrics)}. Omit `fabrics` to allow all fabrics or select"
                    f" some of the valid options: {sorted(valid_fabrics)}"
                ),
            )

    def create_backend(
        self, project_name: str, config: NebiusBackendConfigWithCreds
    ) -> BackendRecord:
        return BackendRecord(
            config=NebiusStoredConfig(
                **NebiusBackendConfig.__response__.parse_obj(config).dict()
            ).json(),
            auth=NebiusCreds.parse_obj(config.creds).json(),
        )

    def get_backend_config_with_creds(self, record: BackendRecord) -> NebiusBackendConfigWithCreds:
        config = self._get_config(record)
        return NebiusBackendConfigWithCreds.__response__.parse_obj(config)

    def get_backend_config_without_creds(self, record: BackendRecord) -> NebiusBackendConfig:
        config = self._get_config(record)
        return NebiusBackendConfig.__response__.parse_obj(config)

    def get_backend(self, record: BackendRecord) -> NebiusBackend:
        config = self._get_config(record)
        return NebiusBackend(config=config)

    def _get_config(self, record: BackendRecord) -> NebiusConfig:
        return NebiusConfig.__response__(
            **json.loads(record.config),
            creds=NebiusCreds.parse_raw(record.auth),
        )
