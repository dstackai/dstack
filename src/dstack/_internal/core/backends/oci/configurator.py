import json
from typing import Dict, Iterable, List, Set, Tuple

from dstack._internal.core.backends.base.configurator import (
    BackendRecord,
    Configurator,
    raise_invalid_credentials_error,
)
from dstack._internal.core.backends.oci import resources
from dstack._internal.core.backends.oci.backend import OCIBackend
from dstack._internal.core.backends.oci.exceptions import any_oci_exception
from dstack._internal.core.backends.oci.models import (
    AnyOCIBackendConfig,
    OCIBackendConfig,
    OCIBackendConfigWithCreds,
    OCIConfig,
    OCICreds,
    OCIDefaultCreds,
    OCIStoredConfig,
)
from dstack._internal.core.backends.oci.region import (
    get_subscribed_regions,
    make_region_client,
    make_region_clients_map,
)
from dstack._internal.core.errors import ServerClientError
from dstack._internal.core.models.backends.base import (
    BackendType,
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
    TYPE = BackendType.OCI
    BACKEND_CLASS = OCIBackend

    def validate_config(self, config: OCIBackendConfigWithCreds, default_creds_enabled: bool):
        if isinstance(config.creds, OCIDefaultCreds) and not default_creds_enabled:
            raise_invalid_credentials_error(
                fields=[["creds"]],
                details="Default credentials are forbidden by dstack settings",
            )
        try:
            get_subscribed_regions(config.creds).names
        except any_oci_exception as e:
            raise_invalid_credentials_error(fields=[["creds"]], details=e)

    def create_backend(
        self, project_name: str, config: OCIBackendConfigWithCreds
    ) -> BackendRecord:
        try:
            subscribed_regions = get_subscribed_regions(config.creds)
        except any_oci_exception as e:
            raise_invalid_credentials_error(fields=[["creds"]], details=e)

        if config.regions is None:
            config.regions = _filter_supported_regions(subscribed_regions.names)
        else:
            _raise_if_regions_unavailable(config.regions, subscribed_regions.names)

        compartment_id, subnet_ids_per_region = _create_resources(
            project_name, config, subscribed_regions.home_region_name
        )
        config.compartment_id = compartment_id
        stored_config = OCIStoredConfig.__response__(
            **config.dict(), subnet_ids_per_region=subnet_ids_per_region
        )

        return BackendRecord(
            config=stored_config.json(),
            auth=OCICreds.parse_obj(config.creds).json(),
        )

    def get_backend_config(
        self, record: BackendRecord, include_creds: bool
    ) -> AnyOCIBackendConfig:
        config = self._get_config(record)
        if include_creds:
            return OCIBackendConfigWithCreds.__response__.parse_obj(config)
        return OCIBackendConfig.__response__.parse_obj(config)

    def get_backend(self, record: BackendRecord) -> OCIBackend:
        config = self._get_config(record)
        return OCIBackend(config=config)

    def _get_config(self, record: BackendRecord) -> OCIConfig:
        return OCIConfig.__response__(
            **json.loads(record.config),
            creds=OCICreds.parse_raw(record.auth).__root__,
        )


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
    project_name: str, config: OCIBackendConfigWithCreds, home_region: str
) -> Tuple[str, Dict[str, str]]:
    compartment_id = config.compartment_id
    if not compartment_id:
        home_region_client = make_region_client(home_region, config.creds)
        compartment_id = resources.get_or_create_compartment(
            f"dstack-{project_name}",
            home_region_client.client_config["tenancy"],
            home_region_client.identity_client,
        ).id

    region_clients = make_region_clients_map(config.regions, config.creds)
    resources.wait_until_compartment_active(compartment_id, region_clients)
    subnets_per_region = resources.set_up_network_resources(
        compartment_id, project_name, region_clients
    )

    return compartment_id, subnets_per_region
