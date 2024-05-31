import base64
import time
from concurrent.futures import Executor, ThreadPoolExecutor, as_completed
from functools import reduce
from itertools import islice
from typing import Dict, Iterable, List, Mapping, Optional, Set, Tuple

import oci

from dstack import version
from dstack._internal.core.backends.oci.region import OCIRegionClient
from dstack._internal.core.errors import BackendError
from dstack._internal.core.models.instances import InstanceOffer
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)
LIST_SHAPES_MAX_LIMIT = 100
CAPACITY_REPORT_MAX_SHAPES = 10  # undocumented, found by experiment
VCN_CIDR = "10.0.0.0/16"
WAIT_FOR_COMPARTMENT_ATTEMPS = 36
WAIT_FOR_COMPARTMENT_DELAY = 5


class ShapesQuota:
    def __init__(self, region_to_domain_to_shape_names: Dict[str, Dict[str, Set[str]]]):
        self._domain_to_shape_names = {
            domain: shape_names
            for domain_to_shape_names in region_to_domain_to_shape_names.values()
            for domain, shape_names in domain_to_shape_names.items()
        }
        self._region_to_shape_names = {
            region_name: reduce(set.union, domain_to_shape_names.values())
            for region_name, domain_to_shape_names in region_to_domain_to_shape_names.items()
        }

    def is_within_region_quota(self, shape_name: str, region_name: str) -> bool:
        return shape_name in self._region_to_shape_names.get(region_name, set())

    def is_within_domain_quota(self, shape_name: str, domain_name: str) -> bool:
        return shape_name in self._domain_to_shape_names.get(domain_name, set())

    @staticmethod
    def load(regions: Mapping[str, OCIRegionClient], compartment_id: str) -> "ShapesQuota":
        with ThreadPoolExecutor(max_workers=8) as executor:
            return ShapesQuota(list_shapes(regions, compartment_id, executor))


def list_shapes_in_domain(
    availability_domain_name: str, client: oci.core.ComputeClient, compartment_id: str
) -> Set[str]:
    """
    Returns a set of shape names allowed to be used in `availability_domain_name`.
    """

    shape_names = set()
    page_id = oci.core.compute_client.missing  # first page

    while page_id is not None:
        resp = client.list_shapes(
            availability_domain=availability_domain_name,
            compartment_id=compartment_id,
            limit=LIST_SHAPES_MAX_LIMIT,
            page=page_id,
        )
        shape_names = shape_names.union(shape.shape for shape in resp.data)
        page_id = resp.headers.get("opc-next-page")

    return shape_names


def list_shapes_in_region(region: OCIRegionClient, compartment_id: str) -> Dict[str, Set[str]]:
    """
    Returns a mapping of availability domain names to sets of shape names
    allowed to be used in these domains.
    """

    result = {}
    for availability_domain in region.availability_domains:
        result[availability_domain.name] = list_shapes_in_domain(
            availability_domain.name, region.compute_client, compartment_id
        )
    return result


def list_shapes(
    regions: Mapping[str, OCIRegionClient], compartment_id: str, executor: Executor
) -> Dict[str, Dict[str, Set[str]]]:
    """
    Returns a mapping of region names to mappings of availability domain names
    to sets of shape names allowed to be used in these availability domains.
    """

    future_to_region_name = {}
    for region_name, region_client in regions.items():
        future = executor.submit(list_shapes_in_region, region_client, compartment_id)
        future_to_region_name[future] = region_name

    result = {}
    for future in as_completed(future_to_region_name):
        region_name = future_to_region_name[future]
        result[region_name] = future.result()

    return result


def check_availability_in_domain(
    shape_names: Iterable[str],
    availability_domain_name: str,
    client: oci.core.ComputeClient,
    compartment_id: str,
) -> Set[str]:
    """
    Returns a subset of `shape_names` with only the shapes available in
    `availability_domain_name`.
    """

    unchecked = set(shape_names)
    available = set()

    while chunk := set(islice(unchecked, CAPACITY_REPORT_MAX_SHAPES)):
        unchecked -= chunk
        report: oci.core.models.ComputeCapacityReport = client.create_compute_capacity_report(
            oci.core.models.CreateComputeCapacityReportDetails(
                compartment_id=compartment_id,
                availability_domain=availability_domain_name,
                shape_availabilities=[
                    oci.core.models.CreateCapacityReportShapeAvailabilityDetails(
                        instance_shape=shape_name,
                    )
                    for shape_name in chunk
                ],
            )
        ).data
        item: oci.core.models.CapacityReportShapeAvailability

        for item in report.shape_availabilities:
            if item.availability_status == item.AVAILABILITY_STATUS_AVAILABLE:
                available.add(item.instance_shape)

    return available


def check_availability_in_region(
    shape_names: Iterable[str],
    shapes_quota: ShapesQuota,
    region: OCIRegionClient,
    compartment_id: str,
) -> Set[str]:
    """
    Returns a subset of `shape_names` with only the shapes available in at least
    one availability domain within `region`.
    """

    all_shapes = set(shape_names)
    available_shapes = set()

    for availability_domain in region.availability_domains:
        shapes_to_check = {
            shape
            for shape in all_shapes - available_shapes
            if shapes_quota.is_within_domain_quota(shape, availability_domain.name)
        }
        available_shapes |= check_availability_in_domain(
            shape_names=shapes_to_check,
            availability_domain_name=availability_domain.name,
            client=region.compute_client,
            compartment_id=compartment_id,
        )

    return available_shapes


def get_shapes_availability(
    offers: Iterable[InstanceOffer],
    shapes_quota: ShapesQuota,
    regions: Mapping[str, OCIRegionClient],
    compartment_id: str,
    executor: Executor,
) -> Dict[str, Set[str]]:
    """
    Returns a mapping of region names to sets of shape names available in these
    regions. Only shapes from `offers` are checked.
    """

    shape_names_per_region = {region: set() for region in regions}
    for offer in offers:
        if shapes_quota.is_within_region_quota(offer.instance.name, offer.region):
            shape_names_per_region[offer.region].add(offer.instance.name)

    future_to_region_name = {}
    for region_name, shape_names in shape_names_per_region.items():
        future = executor.submit(
            check_availability_in_region,
            shape_names,
            shapes_quota,
            regions[region_name],
            compartment_id,
        )
        future_to_region_name[future] = region_name

    result = {}
    for future in as_completed(future_to_region_name):
        region_name = future_to_region_name[future]
        result[region_name] = future.result()

    return result


def choose_available_domain(
    shape_name: str, shapes_quota: ShapesQuota, region: OCIRegionClient, compartment_id: str
) -> Optional[str]:
    """
    Returns the name of any availability domain within `region` in which
    `shape_name` is available. None if the shape is unavailable or not within
    `shapes_quota` in all domains.
    """

    for domain in region.availability_domains:
        if shapes_quota.is_within_domain_quota(
            shape_name, domain.name
        ) and check_availability_in_domain(
            {shape_name}, domain.name, region.compute_client, compartment_id
        ):
            return domain.name
    return None


def get_instance_vnic(
    instance_id: str, region: OCIRegionClient, compartment_id: str
) -> Optional[oci.core.models.Vnic]:
    attachments: List[oci.core.models.VnicAttachment] = (
        region.compute_client.list_vnic_attachments(compartment_id, instance_id=instance_id).data
    )
    if not attachments:
        return None
    return region.virtual_network_client.get_vnic(attachments[0].vnic_id).data


def launch_instance(
    region: OCIRegionClient,
    availability_domain: str,
    compartment_id: str,
    subnet_id: str,
    display_name: str,
    cloud_init_user_data: str,
    shape: str,
    disk_size_gb: int,
    image_id: str,
) -> oci.core.models.Instance:
    return region.compute_client.launch_instance(
        oci.core.models.LaunchInstanceDetails(
            availability_domain=availability_domain,
            compartment_id=compartment_id,
            create_vnic_details=oci.core.models.CreateVnicDetails(subnet_id=subnet_id),
            display_name=display_name,
            instance_options=oci.core.models.InstanceOptions(
                are_legacy_imds_endpoints_disabled=True
            ),
            metadata=dict(
                user_data=base64.b64encode(cloud_init_user_data.encode()).decode(),
            ),
            shape=shape,
            source_details=oci.core.models.InstanceSourceViaImageDetails(
                image_id=image_id,
                boot_volume_size_in_gbs=disk_size_gb,
            ),
        )
    ).data


def terminate_instance_if_exists(client: oci.core.ComputeClient, instance_id: str) -> None:
    try:
        client.terminate_instance(
            instance_id=instance_id,
            preserve_boot_volume=False,
            preserve_data_volumes_created_at_launch=False,
        )
    except oci.exceptions.ServiceError as e:
        if e.status != 404:
            raise


def get_marketplace_listing_and_package(
    cuda: bool, client: oci.marketplace.MarketplaceClient
) -> Tuple[oci.marketplace.models.Listing, oci.marketplace.models.ImageListingPackage]:
    listing_name = f"dstack-{version.base_image}"
    if cuda:
        listing_name = f"dstack-cuda-{version.base_image}"

    listing_summaries: List[oci.marketplace.models.ListingSummary] = client.list_listings(
        name=listing_name,
        listing_types=[oci.marketplace.models.Listing.LISTING_TYPE_COMMUNITY],
        limit=1000,
    ).data
    # filter by exact match, as list_listings seems to filter by substring
    listing_summaries = [s for s in listing_summaries if s.name == listing_name]

    if len(listing_summaries) != 1:
        msg = f"Expected to find 1 listing by name {listing_name}, found {len(listing_summaries)}"
        raise BackendError(msg)

    listing: oci.marketplace.models.Listing = client.get_listing(listing_summaries[0].id).data
    package = client.get_package(listing.id, listing.default_package_version).data
    return listing, package


def accept_marketplace_listing_agreements(
    listing: oci.marketplace.models.Listing,
    compartment_id: str,
    client: oci.marketplace.MarketplaceClient,
) -> None:
    accepted_agreements: List[oci.marketplace.models.AcceptedAgreementSummary] = (
        client.list_accepted_agreements(
            compartment_id=compartment_id,
            listing_id=listing.id,
            package_version=listing.default_package_version,
        ).data
    )
    accepted_agreement_ids = {a.agreement_id for a in accepted_agreements}
    agreement_summaries: List[oci.marketplace.models.AgreementSummary] = client.list_agreements(
        listing.id, listing.default_package_version
    ).data
    for agreement_summary in agreement_summaries:
        if agreement_summary.id in accepted_agreement_ids:
            continue
        agreement: oci.marketplace.models.Agreement = client.get_agreement(
            listing_id=listing.id,
            package_version=listing.default_package_version,
            agreement_id=agreement_summary.id,
            compartment_id=compartment_id,
        ).data
        client.create_accepted_agreement(
            oci.marketplace.models.CreateAcceptedAgreementDetails(
                compartment_id=compartment_id,
                listing_id=listing.id,
                package_version=listing.default_package_version,
                agreement_id=agreement_summary.id,
                signature=agreement.signature,
            )
        )


def get_or_create_compartment(
    name: str, parent_compartment_id: str, client: oci.identity.IdentityClient
) -> oci.identity.models.Compartment:
    if compartments := client.list_compartments(
        compartment_id=parent_compartment_id, name=name
    ).data:
        return compartments[0]

    return client.create_compartment(
        oci.identity.models.CreateCompartmentDetails(
            compartment_id=parent_compartment_id,
            name=name,
            description="Resources created and managed by dstack",
        )
    ).data


def get_compartment_lifecycle_state(id: str, client: oci.identity.IdentityClient) -> Optional[str]:
    try:
        return client.get_compartment(id).data.lifecycle_state
    except oci.exceptions.ServiceError as e:
        if e.status == 404:
            return None
        raise


def wait_until_compartment_active(id: str, regions: Mapping[str, OCIRegionClient]) -> None:
    start_time = int(time.time())
    state_active = oci.identity.models.Compartment.LIFECYCLE_STATE_ACTIVE
    state_creating = oci.identity.models.Compartment.LIFECYCLE_STATE_CREATING
    pending_regions = set(regions)

    for attempt in range(1, WAIT_FOR_COMPARTMENT_ATTEMPS + 1):
        while region := next(iter(pending_regions), None):
            state = get_compartment_lifecycle_state(id, regions[region].identity_client)
            if state == state_active:
                pending_regions.remove(region)
            elif state == state_creating or state is None:
                break
            else:
                msg = f"Unexpected state {state} for compartment {id}"
                raise BackendError(msg)

        if not pending_regions:
            return

        logger.debug(
            f"Waiting for OCI compartment {id} to become active. "
            f"Tried {attempt}/{WAIT_FOR_COMPARTMENT_ATTEMPS} times"
        )
        if attempt != WAIT_FOR_COMPARTMENT_ATTEMPS:
            time.sleep(WAIT_FOR_COMPARTMENT_DELAY)

    time_spent = int(time.time() - start_time)
    msg = f"Compartment {id} did not become active in {time_spent}s. Giving up"
    raise BackendError(msg)


def set_up_network_resources(
    compartment_id: str, project_name: str, regions: Mapping[str, OCIRegionClient]
) -> Dict[str, str]:
    """
    Create or update a VCN and a subnet with Internet access in each region.
    Returns a mapping of region names to subnet IDs.
    """

    with ThreadPoolExecutor(max_workers=8) as executor:
        future_to_region_name = {}
        for region_name, region_client in regions.items():
            future = executor.submit(
                set_up_network_resources_in_region,
                compartment_id,
                project_name,
                region_client.virtual_network_client,
            )
            future_to_region_name[future] = region_name

        result = {}
        for future in as_completed(future_to_region_name):
            region_name = future_to_region_name[future]
            result[region_name] = future.result()

    return result


def set_up_network_resources_in_region(
    compartment_id: str, project_name: str, client: oci.core.VirtualNetworkClient
) -> str:
    """
    Create or update a VCN and a subnet with Internet access. Returns subnet ID.
    """

    vcn = get_or_create_vcn(f"dstack-{project_name}-default-vcn", compartment_id, client)
    internet_gateway = get_or_create_internet_gateway(
        f"dstack-{project_name}-default-internet-gateway", vcn.id, compartment_id, client
    )
    update_route_table(vcn.default_route_table_id, internet_gateway.id, client)
    subnet = get_or_create_subnet(
        f"dstack-{project_name}-default-subnet", vcn.id, compartment_id, client
    )
    return subnet.id


def get_or_create_vcn(
    name: str, compartment_id: str, client: oci.core.VirtualNetworkClient
) -> oci.core.models.Vcn:
    if vcns := client.list_vcns(compartment_id=compartment_id, display_name=name).data:
        return vcns[0]

    return client.create_vcn(
        oci.core.models.CreateVcnDetails(
            cidr_blocks=[VCN_CIDR],
            compartment_id=compartment_id,
            display_name=name,
        )
    ).data


def get_or_create_subnet(
    name: str, vcn_id: str, compartment_id: str, client: oci.core.VirtualNetworkClient
) -> oci.core.models.Subnet:
    if subnets := client.list_subnets(compartment_id=compartment_id, display_name=name).data:
        return subnets[0]

    return client.create_subnet(
        oci.core.models.CreateSubnetDetails(
            cidr_block=VCN_CIDR,
            compartment_id=compartment_id,
            display_name=name,
            vcn_id=vcn_id,
        )
    ).data


def get_or_create_internet_gateway(
    name: str, vcn_id: str, compartment_id: str, client: oci.core.VirtualNetworkClient
) -> oci.core.models.InternetGateway:
    if gateways := client.list_internet_gateways(
        compartment_id=compartment_id, vcn_id=vcn_id, display_name=name
    ).data:
        return gateways[0]

    return client.create_internet_gateway(
        oci.core.models.CreateInternetGatewayDetails(
            compartment_id=compartment_id, display_name=name, vcn_id=vcn_id, is_enabled=True
        )
    ).data


def update_route_table(
    route_table_id: str, internet_gateway_id: str, client: oci.core.VirtualNetworkClient
) -> oci.core.models.RouteTable:
    return client.update_route_table(
        route_table_id,
        oci.core.models.UpdateRouteTableDetails(
            route_rules=[
                oci.core.models.RouteRule(
                    destination="0.0.0.0/0", network_entity_id=internet_gateway_id
                )
            ]
        ),
    ).data
