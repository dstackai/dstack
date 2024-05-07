import json
from typing import List

from dstack._internal.core.backends.oci import OCIBackend, auth
from dstack._internal.core.backends.oci.config import OCIConfig
from dstack._internal.core.backends.oci.exceptions import any_oci_exception
from dstack._internal.core.backends.oci.region import get_subscribed_region_names
from dstack._internal.core.errors import ServerClientError
from dstack._internal.core.models.backends.base import (
    BackendType,
    ConfigElementValue,
    ConfigMultiElement,
)
from dstack._internal.core.models.backends.oci import (
    AnyOCIConfigInfo,
    OCIConfigInfo,
    OCIConfigInfoWithCreds,
    OCIConfigInfoWithCredsPartial,
    OCIConfigValues,
    OCICreds,
    OCIDefaultCreds,
    OCIStoredConfig,
)
from dstack._internal.core.models.common import is_core_model_instance
from dstack._internal.server import settings
from dstack._internal.server.models import BackendModel, ProjectModel
from dstack._internal.server.services.backends.configurators.base import (
    Configurator,
    raise_invalid_credentials_error,
)
from dstack._internal.settings import FeatureFlags


class OCIConfigurator(Configurator):
    if FeatureFlags.OCI_BACKEND:
        TYPE: BackendType = BackendType.OCI

    def get_default_configs(self) -> List[OCIConfigInfoWithCreds]:
        creds = OCIDefaultCreds()
        try:
            regions = get_subscribed_region_names(creds)
        except any_oci_exception:
            return []
        return [
            OCIConfigInfoWithCreds(
                regions=regions,
                creds=creds,
            )
        ]

    def get_config_values(self, config: OCIConfigInfoWithCredsPartial) -> OCIConfigValues:
        config_values = OCIConfigValues(regions=None)
        config_values.default_creds = (
            settings.DEFAULT_CREDS_ENABLED and auth.default_creds_available()
        )
        if config.creds is None:
            return config_values
        if (
            is_core_model_instance(config.creds, OCIDefaultCreds)
            and not settings.DEFAULT_CREDS_ENABLED
        ):
            raise_invalid_credentials_error(fields=[["creds"]])

        try:
            available_regions = get_subscribed_region_names(config.creds)
        except any_oci_exception:
            raise_invalid_credentials_error(fields=[["creds"]])

        if config.regions:
            selected_regions = [r for r in config.regions if r in available_regions]
        else:
            selected_regions = available_regions

        config_values.regions = self._get_regions_element(
            available=available_regions,
            selected=selected_regions,
        )
        return config_values

    def create_backend(
        self, project: ProjectModel, config: OCIConfigInfoWithCreds
    ) -> BackendModel:
        try:
            available_regions = get_subscribed_region_names(config.creds)
        except any_oci_exception:
            raise_invalid_credentials_error(fields=[["creds"]])

        if config.regions is None:
            config.regions = available_regions
        elif unsubscribed_regions := set(config.regions) - set(available_regions):
            msg = f"Regions {unsubscribed_regions} are configured but not subscribed to in OCI"
            raise ServerClientError(msg, fields=[["regions"]])

        return BackendModel(
            project_id=project.id,
            type=self.TYPE.value,
            config=OCIStoredConfig.__response__.parse_obj(config).json(),
            auth=OCICreds.parse_obj(config.creds).json(),
        )

    def get_config_info(self, model: BackendModel, include_creds: bool) -> AnyOCIConfigInfo:
        config = self._get_backend_config(model)
        if include_creds:
            return OCIConfigInfoWithCreds.__response__.parse_obj(config)
        return OCIConfigInfo.__response__.parse_obj(config)

    def get_backend(self, model: BackendModel) -> OCIBackend:
        config = self._get_backend_config(model)
        return OCIBackend(config=config)

    def _get_backend_config(self, model: BackendModel) -> OCIConfig:
        return OCIConfig.__response__(
            **json.loads(model.config),
            creds=OCICreds.parse_raw(model.auth).__root__,
        )

    def _get_regions_element(
        self, available: List[str], selected: List[str]
    ) -> ConfigMultiElement:
        element = ConfigMultiElement(selected=selected)
        for region in available:
            element.values.append(ConfigElementValue(value=region, label=region))
        return element
