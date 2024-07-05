import json
from typing import Dict, Iterable, List, Set, Tuple

from dstack._internal.core.backends.oci import OCIBackend, auth, resources
from dstack._internal.core.backends.oci.config import OCIConfig
from dstack._internal.core.backends.oci.exceptions import any_oci_exception
from dstack._internal.core.backends.oci.region import (
    get_subscribed_regions,
    make_region_client,
    make_region_clients_map,
)
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

# where dstack images are published
SUPPORTED_REGIONS = frozenset(
    [
        "eu-frankfurt-1",
        "eu-milan-1",
        "me-dubai-1",
        "uk-london-1",
        "us-ashburn-1",
        "us-chicago-1",
        "us-phoenix-1",
    ]
)


class OCIConfigurator(Configurator):
    TYPE: BackendType = BackendType.OCI

    def get_default_configs(self) -> List[OCIConfigInfoWithCreds]:
        creds = OCIDefaultCreds()
        try:
            subscribed_regions = get_subscribed_regions(creds).names
        except any_oci_exception:
            return []
        return [
            OCIConfigInfoWithCreds(
                regions=list(subscribed_regions & SUPPORTED_REGIONS),
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
            raise_invalid_credentials_error(
                fields=[["creds"]],
                details="Default credentials are forbidden by dstack settings",
            )

        try:
            available_regions = get_subscribed_regions(config.creds).names & SUPPORTED_REGIONS
        except any_oci_exception as e:
            raise_invalid_credentials_error(fields=[["creds"]], details=e)

        if config.regions:
            selected_regions = [r for r in config.regions if r in available_regions]
        else:
            selected_regions = list(available_regions)

        config_values.regions = self._get_regions_element(
            available=available_regions,
            selected=selected_regions,
        )
        return config_values

    def create_backend(
        self, project: ProjectModel, config: OCIConfigInfoWithCreds
    ) -> BackendModel:
        try:
            subscribed_regions = get_subscribed_regions(config.creds)
        except any_oci_exception as e:
            raise_invalid_credentials_error(fields=[["creds"]], details=e)

        if config.regions is None:
            config.regions = _filter_supported_regions(subscribed_regions.names)
        else:
            _raise_if_regions_unavailable(config.regions, subscribed_regions.names)

        compartment_id, subnet_ids_per_region = _create_resources(
            project, config, subscribed_regions.home_region_name
        )
        config.compartment_id = compartment_id
        stored_config = OCIStoredConfig.__response__(
            **config.dict(), subnet_ids_per_region=subnet_ids_per_region
        )

        return BackendModel(
            project_id=project.id,
            type=self.TYPE.value,
            config=stored_config.json(),
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
        self, available: Iterable[str], selected: List[str]
    ) -> ConfigMultiElement:
        element = ConfigMultiElement(selected=selected)
        for region in available:
            element.values.append(ConfigElementValue(value=region, label=region))
        return element


def _filter_supported_regions(subscribed_region_names: Set[str]) -> List[str]:
    available_regions = subscribed_region_names & SUPPORTED_REGIONS
    if not available_regions:
        msg = (
            f"None of your subscribed regions {subscribed_region_names} are supported "
            "by dstack yet. Please subscribe to a supported region in OCI Console or "
            "contact dstack if you need a specific region to become supported. "
            f"Currently supported regions are: {set(SUPPORTED_REGIONS)}"
        )
        raise ServerClientError(msg)
    return list(available_regions)


def _raise_if_regions_unavailable(
    region_names: Iterable[str], subscribed_region_names: Set[str]
) -> None:
    region_names = set(region_names)
    if unsupported_regions := region_names - SUPPORTED_REGIONS:
        msg = (
            f"Regions {unsupported_regions} are configured but not supported by dstack yet. "
            f"Only these regions are supported: {set(SUPPORTED_REGIONS)}. "
            "Please contact dstack if a region you need is missing."
        )
        raise ServerClientError(msg, fields=[["regions"]])
    if unsubscribed_regions := region_names - subscribed_region_names:
        msg = f"Regions {unsubscribed_regions} are configured but not subscribed to in OCI"
        raise ServerClientError(msg, fields=[["regions"]])


def _create_resources(
    project: ProjectModel, config: OCIConfigInfoWithCreds, home_region: str
) -> Tuple[str, Dict[str, str]]:
    compartment_id = config.compartment_id
    if not compartment_id:
        home_region_client = make_region_client(home_region, config.creds)
        compartment_id = resources.get_or_create_compartment(
            f"dstack-{project.name}",
            home_region_client.client_config["tenancy"],
            home_region_client.identity_client,
        ).id

    region_clients = make_region_clients_map(config.regions, config.creds)
    resources.wait_until_compartment_active(compartment_id, region_clients)
    subnets_per_region = resources.set_up_network_resources(
        compartment_id, project.name, region_clients
    )

    return compartment_id, subnets_per_region
