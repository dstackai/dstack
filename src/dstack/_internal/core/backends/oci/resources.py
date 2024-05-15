from concurrent.futures import Executor, as_completed
from itertools import islice
from typing import Dict, Iterable, List, Mapping, Set

import oci

from dstack._internal.core.backends.oci.region import OCIRegionClient
from dstack._internal.core.models.instances import InstanceOffer

LIST_SHAPES_MAX_LIMIT = 100
CAPACITY_REPORT_MAX_SHAPES = 10  # undocumented, found by experiment


def list_shapes(
    client: oci.core.ComputeClient, compartment_id: str
) -> List[oci.core.models.Shape]:
    """
    Lists shapes allowed to be used in the region the `client` is bound to.
    """

    shapes = []
    page = oci.core.compute_client.missing  # first page

    while page is not None:
        resp = client.list_shapes(compartment_id, limit=LIST_SHAPES_MAX_LIMIT, page=page)
        shapes.extend(resp.data)
        page = resp.headers.get("opc-next-page")

    return shapes


def get_shapes_quota(
    regions: Mapping[str, OCIRegionClient], compartment_id: str, executor: Executor
) -> Dict[str, Set[str]]:
    """
    Returns a mapping of region names to sets of shape names allowed to be used
    in these regions.
    """

    future_to_region_name = {}
    for region_name, region_client in regions.items():
        future = executor.submit(list_shapes, region_client.compute_client, compartment_id)
        future_to_region_name[future] = region_name

    result = {}
    for future in as_completed(future_to_region_name):
        region_name = future_to_region_name[future]
        shape_names = {shape.shape for shape in future.result()}
        result[region_name] = shape_names

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
    shape_names: Iterable[str], region: OCIRegionClient, compartment_id: str
) -> Set[str]:
    """
    Returns a subset of `shape_names` with only the shapes available in at least
    one availability domain within `region`.
    """

    all_shapes = set(shape_names)
    available_shapes = set()

    for availability_domain in region.availability_domains:
        available_shapes |= check_availability_in_domain(
            shape_names=all_shapes - available_shapes,
            availability_domain_name=availability_domain.name,
            client=region.compute_client,
            compartment_id=compartment_id,
        )

    return available_shapes


def get_shapes_availability(
    offers: Iterable[InstanceOffer],
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
        shape_names_per_region[offer.region].add(offer.instance.name)

    future_to_region_name = {}
    for region_name, shape_names in shape_names_per_region.items():
        future = executor.submit(
            check_availability_in_region, shape_names, regions[region_name], compartment_id
        )
        future_to_region_name[future] = region_name

    result = {}
    for future in as_completed(future_to_region_name):
        region_name = future_to_region_name[future]
        result[region_name] = future.result()

    return result
