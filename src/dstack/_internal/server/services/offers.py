import itertools
from collections.abc import Iterable, Iterator
from typing import List, Literal, Optional, Tuple, Union

import gpuhunt

from dstack._internal.core.backends.base.backend import Backend
from dstack._internal.core.backends.base.compute import ComputeWithPlacementGroupSupport
from dstack._internal.core.backends.features import (
    BACKENDS_WITH_CREATE_INSTANCE_SUPPORT,
    BACKENDS_WITH_MULTINODE_SUPPORT,
    BACKENDS_WITH_PRIVILEGED_SUPPORT,
    BACKENDS_WITH_RESERVATION_SUPPORT,
)
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import (
    InstanceOfferWithAvailability,
    InstanceType,
    Resources,
)
from dstack._internal.core.models.placement import PlacementGroup
from dstack._internal.core.models.profiles import Profile
from dstack._internal.core.models.runs import JobProvisioningData, Requirements
from dstack._internal.core.models.volumes import Volume
from dstack._internal.server.models import ProjectModel
from dstack._internal.server.services import backends as backends_services


async def get_offers_by_requirements(
    project: ProjectModel,
    profile: Profile,
    requirements: Requirements,
    exclude_not_available=False,
    multinode: bool = False,
    master_job_provisioning_data: Optional[JobProvisioningData] = None,
    volumes: Optional[List[List[Volume]]] = None,
    privileged: bool = False,
    instance_mounts: bool = False,
    placement_group: Optional[PlacementGroup] = None,
    blocks: Union[int, Literal["auto"]] = 1,
    max_offers: Optional[int] = None,
) -> List[Tuple[Backend, InstanceOfferWithAvailability]]:
    backends: List[Backend] = await backends_services.get_project_backends(project=project)

    backend_types = profile.backends
    regions = profile.regions
    availability_zones = profile.availability_zones
    instance_types = profile.instance_types

    if volumes:
        mount_point_volumes = volumes[0]
        volumes_backend_types = [v.configuration.backend for v in mount_point_volumes]
        if backend_types is None:
            backend_types = volumes_backend_types
        backend_types = [b for b in backend_types if b in volumes_backend_types]
        volumes_regions = [v.configuration.region for v in mount_point_volumes]
        if regions is None:
            regions = volumes_regions
        regions = [r for r in regions if r in volumes_regions]

    if multinode:
        if backend_types is None:
            backend_types = BACKENDS_WITH_MULTINODE_SUPPORT
        backend_types = [b for b in backend_types if b in BACKENDS_WITH_MULTINODE_SUPPORT]

    if privileged:
        if backend_types is None:
            backend_types = BACKENDS_WITH_PRIVILEGED_SUPPORT
        backend_types = [b for b in backend_types if b in BACKENDS_WITH_PRIVILEGED_SUPPORT]

    if instance_mounts:
        if backend_types is None:
            backend_types = BACKENDS_WITH_CREATE_INSTANCE_SUPPORT
        backend_types = [b for b in backend_types if b in BACKENDS_WITH_CREATE_INSTANCE_SUPPORT]

    if profile.reservation is not None:
        if backend_types is None:
            backend_types = BACKENDS_WITH_RESERVATION_SUPPORT
        backend_types = [b for b in backend_types if b in BACKENDS_WITH_RESERVATION_SUPPORT]

    # For multi-node, restrict backend and region.
    # The default behavior is to provision all nodes in the same backend and region.
    if master_job_provisioning_data is not None:
        if backend_types is None:
            backend_types = [master_job_provisioning_data.get_base_backend()]
        if regions is None:
            regions = [master_job_provisioning_data.region]
        backend_types = [
            b for b in backend_types if b == master_job_provisioning_data.get_base_backend()
        ]
        regions = [r for r in regions if r == master_job_provisioning_data.region]

    if backend_types is not None:
        backends = [b for b in backends if b.TYPE in backend_types or b.TYPE == BackendType.DSTACK]

    offers = await backends_services.get_backend_offers(
        backends=backends,
        requirements=requirements,
        exclude_not_available=exclude_not_available,
    )

    offers = _filter_offers(
        offers=offers,
        # Double filtering by backends if backend returns offers for other backend.
        backend_types=backend_types,
        regions=regions,
        availability_zones=availability_zones,
        instance_types=instance_types,
        placement_group=placement_group,
    )

    if blocks != 1:
        offers = _get_shareable_offers(offers, blocks)

    if max_offers is not None:
        offers = itertools.islice(offers, max_offers)

    # Put NOT_AVAILABLE and NO_QUOTA offers at the end.
    # We have to do this after taking max_offers to avoid processing all offers
    # if all/most offers are unavailable.
    return sorted(offers, key=lambda i: not i[1].availability.is_available())


def is_divisible_into_blocks(
    cpu_count: int, gpu_count: int, blocks: Union[int, Literal["auto"]]
) -> tuple[bool, int]:
    """
    Returns `True` and number of blocks the instance can be split into or `False` and `0` if
    is not divisible.
    Requested number of blocks can be `auto`, which means as many as possible.
    """
    if blocks == "auto":
        if gpu_count == 0:
            blocks = cpu_count
        else:
            blocks = min(cpu_count, gpu_count)
    if blocks < 1 or cpu_count % blocks or gpu_count % blocks:
        return False, 0
    return True, blocks


def generate_shared_offer(
    offer: InstanceOfferWithAvailability, blocks: int, total_blocks: int
) -> InstanceOfferWithAvailability:
    full_resources = offer.instance.resources
    resources = Resources(
        cpus=full_resources.cpus // total_blocks * blocks,
        memory_mib=full_resources.memory_mib // total_blocks * blocks,
        gpus=full_resources.gpus[: len(full_resources.gpus) // total_blocks * blocks],
        spot=full_resources.spot,
        disk=full_resources.disk,
        description=full_resources.description,
    )
    return InstanceOfferWithAvailability(
        backend=offer.backend,
        instance=InstanceType(
            name=offer.instance.name,
            resources=resources,
        ),
        region=offer.region,
        price=offer.price,
        backend_data=offer.backend_data,
        availability=offer.availability,
        blocks=blocks,
        total_blocks=total_blocks,
    )


def get_instance_offer_with_restricted_az(
    instance_offer: InstanceOfferWithAvailability,
    master_job_provisioning_data: Optional[JobProvisioningData],
) -> InstanceOfferWithAvailability:
    instance_offer = instance_offer.copy()
    if (
        master_job_provisioning_data is not None
        and master_job_provisioning_data.availability_zone is not None
    ):
        if instance_offer.availability_zones is None:
            instance_offer.availability_zones = [master_job_provisioning_data.availability_zone]
        instance_offer.availability_zones = [
            z
            for z in instance_offer.availability_zones
            if z == master_job_provisioning_data.availability_zone
        ]
    return instance_offer


def _filter_offers(
    offers: Iterable[Tuple[Backend, InstanceOfferWithAvailability]],
    backend_types: Optional[List[BackendType]] = None,
    regions: Optional[List[str]] = None,
    availability_zones: Optional[List[str]] = None,
    instance_types: Optional[List[str]] = None,
    placement_group: Optional[PlacementGroup] = None,
) -> Iterator[Tuple[Backend, InstanceOfferWithAvailability]]:
    """
    Yields filtered offers. May return modified offers to match the filters.
    """
    if regions is not None:
        regions = [r.lower() for r in regions]
    if instance_types is not None:
        instance_types = [i.lower() for i in instance_types]

    for b, offer in offers:
        if backend_types is not None and offer.backend not in backend_types:
            continue
        if regions is not None and offer.region.lower() not in regions:
            continue
        if instance_types is not None and offer.instance.name.lower() not in instance_types:
            continue
        if placement_group is not None:
            compute = b.compute()
            if not isinstance(
                compute, ComputeWithPlacementGroupSupport
            ) or not compute.is_suitable_placement_group(placement_group, offer):
                continue
        if availability_zones is not None:
            if offer.availability_zones is None:
                continue
            new_offer = offer.copy()
            new_offer.availability_zones = [
                z for z in offer.availability_zones if z in availability_zones
            ]
            if not new_offer.availability_zones:
                continue
            offer = new_offer
        yield (b, offer)


def _get_shareable_offers(
    offers: Iterable[Tuple[Backend, InstanceOfferWithAvailability]],
    blocks: Union[int, Literal["auto"]],
) -> Iterator[Tuple[Backend, InstanceOfferWithAvailability]]:
    """
    Yields offers that can be shared with `total_blocks` set.
    """
    for backend, offer in offers:
        resources = offer.instance.resources
        cpu_count = resources.cpus
        gpu_count = len(resources.gpus)
        if gpu_count > 0 and resources.gpus[0].vendor == gpuhunt.AcceleratorVendor.GOOGLE:
            # TPUs cannot be shared
            gpu_count = 1
        divisible, total_blocks = is_divisible_into_blocks(cpu_count, gpu_count, blocks)
        if not divisible:
            continue
        new_offer = offer.copy()
        new_offer.total_blocks = total_blocks
        yield (backend, new_offer)
