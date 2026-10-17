import heapq
import itertools
from collections.abc import Container, Iterable, Iterator
from dataclasses import dataclass
from typing import List, Literal, Optional, Tuple, TypeVar, Union

import gpuhunt

from dstack._internal.core.backends.base.backend import Backend
from dstack._internal.core.backends.base.compute import ComputeWithPlacementGroupSupport
from dstack._internal.core.backends.features import (
    BACKENDS_WITH_INSTANCE_VOLUMES_SUPPORT,
    BACKENDS_WITH_MULTINODE_SUPPORT,
    BACKENDS_WITH_PRIVILEGED_SUPPORT,
    BACKENDS_WITH_RESERVATION_SUPPORT,
)
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import (
    InstanceAvailability,
    InstanceOfferWithAvailability,
    InstanceType,
    Resources,
)
from dstack._internal.core.models.placement import PlacementGroup
from dstack._internal.core.models.profiles import Profile
from dstack._internal.core.models.runs import JobProvisioningData, Requirements
from dstack._internal.core.models.volumes import Volume, VolumeConfigurationWithRegion
from dstack._internal.server.models import ProjectModel
from dstack._internal.server.services import backends as backends_services
from dstack._internal.utils.common import run_async


@dataclass
class Offers:
    offers: list[tuple[Backend, InstanceOfferWithAvailability]]
    unavailable_reason: Optional[InstanceAvailability] = None
    """Common reason for excluded matching offers if none are available; None otherwise."""


async def get_offers_by_requirements(
    project: ProjectModel,
    profile: Profile,
    requirements: Requirements,
    exclude_not_available: bool = False,
    multinode: bool = False,
    master_job_provisioning_data: Optional[JobProvisioningData] = None,
    volumes: Optional[List[List[Volume]]] = None,
    privileged: bool = False,
    instance_mounts: bool = False,
    placement_group: Optional[PlacementGroup] = None,
    blocks: Union[int, Literal["auto"]] = 1,
    max_offers: Optional[int] = None,
    full_offers: bool = False,
    unallocated_resources: bool = False,
    supported_backend_types: Optional[Container[BackendType]] = None,
) -> Offers:
    backends: List[Backend] = await backends_services.get_project_backends(project=project)

    backend_types: Optional[list[BackendType]] = profile.backends
    regions: Optional[list[str]] = profile.regions
    availability_zones: Optional[list[str]] = profile.availability_zones
    instance_types: Optional[list[str]] = profile.instance_types
    # (BackendType, region.lower() | None). None means any region.
    volumes_locations: Optional[set[tuple[BackendType, Optional[str]]]] = None

    if volumes:
        volumes_locations = {
            (
                v.get_backend(),
                v.get_region().lower()
                if isinstance(v.configuration, VolumeConfigurationWithRegion)
                else None,
            )
            for v in volumes[0]
        }

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
            backend_types = BACKENDS_WITH_INSTANCE_VOLUMES_SUPPORT
        backend_types = [b for b in backend_types if b in BACKENDS_WITH_INSTANCE_VOLUMES_SUPPORT]

    if requirements.reservation is not None:
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

    offer_filter = _OfferFilter(
        backend_types=backend_types,
        regions=None if regions is None else [r.lower() for r in regions],
        availability_zones=None
        if availability_zones is None
        else [z.lower() for z in availability_zones],
        instance_types=None if instance_types is None else [i.lower() for i in instance_types],
        placement_group=placement_group,
        volumes_locations=volumes_locations,
        supported_backend_types=supported_backend_types,
    )

    offers_by_backend = await backends_services.get_backend_offers(
        backends=backends,
        requirements=requirements,
        full_offers=full_offers,
        unallocated_resources=unallocated_resources,
    )
    return await run_async(
        _select_offers, offers_by_backend, offer_filter, blocks, exclude_not_available, max_offers
    )


def _select_offers(
    offers_by_backend: list[tuple[Backend, Iterable[InstanceOfferWithAvailability]]],
    offer_filter: "_OfferFilter",
    blocks: Union[int, Literal["auto"]],
    exclude_not_available: bool,
    max_offers: Optional[int],
) -> Offers:
    unavailable: set[InstanceAvailability] = set()

    def available_offers(
        backend: Backend, backend_offers: Iterable[InstanceOfferWithAvailability]
    ) -> Iterator[tuple[Backend, InstanceOfferWithAvailability]]:
        for offer in backend_offers:
            if offer.availability.is_available():
                yield backend, offer
            elif (
                offer.availability not in unavailable
                and offer_filter.matches(backend, offer)
                and (blocks == 1 or _get_offer_blocks(offer, blocks)[0])
            ):
                unavailable.add(offer.availability)

    iterables = [
        available_offers(backend, backend_offers)
        if exclude_not_available
        else _with_backend(backend, backend_offers)
        for backend, backend_offers in offers_by_backend
    ]

    # Availability must be filtered before merging to preserve backend-specific order.
    offers = _filter_offers(merge_offer_iterables(*iterables), offer_filter)

    if blocks != 1:
        offers = _get_shareable_offers(offers, blocks)

    if max_offers is not None:
        offers = itertools.islice(offers, max_offers)

    # Put NOT_AVAILABLE and NO_QUOTA offers at the end.
    # We have to do this after taking max_offers to avoid processing all offers
    # if all/most offers are unavailable.
    selected = sorted(offers, key=lambda i: not i[1].availability.is_available())
    unavailable_reason = (
        next(iter(unavailable)) if not selected and len(unavailable) == 1 else None
    )
    return Offers(offers=selected, unavailable_reason=unavailable_reason)


def _with_backend(
    backend: Backend, offers: Iterable[InstanceOfferWithAvailability]
) -> Iterator[tuple[Backend, InstanceOfferWithAvailability]]:
    for offer in offers:
        yield backend, offer


T = TypeVar("T")


def merge_offer_iterables(
    *iterables: Iterable[tuple[T, InstanceOfferWithAvailability]],
) -> Iterable[tuple[T, InstanceOfferWithAvailability]]:
    """
    Merge offers from different sources (e.g., different backends, different fleets).

    Some backends produce offers that are not sorted by price (e.g., `vastai` sorts by pod score).
    That backend-specific order is preserved.
    """
    return heapq.merge(*iterables, key=lambda i: i[1].price)


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
    instance_offer = instance_offer.model_copy()
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


@dataclass
class _OfferFilter:
    backend_types: Optional[List[BackendType]]
    regions: Optional[List[str]]
    availability_zones: Optional[List[str]]
    instance_types: Optional[List[str]]
    placement_group: Optional[PlacementGroup]
    volumes_locations: Optional[Container[tuple[BackendType, Optional[str]]]]
    supported_backend_types: Optional[Container[BackendType]]

    def matches(
        self,
        backend: Backend,
        offer: InstanceOfferWithAvailability,
        check_availability_zones: bool = True,
    ) -> bool:
        # Backends such as dstack can return offers for other backend types.
        if self.backend_types is not None and offer.backend not in self.backend_types:
            return False
        if (
            self.supported_backend_types is not None
            and offer.backend not in self.supported_backend_types
        ):
            return False
        if self.regions is not None and offer.region.lower() not in self.regions:
            return False
        if (
            self.instance_types is not None
            and offer.instance.name.lower() not in self.instance_types
        ):
            return False
        if self.placement_group is not None:
            compute = backend.compute()
            if not isinstance(
                compute, ComputeWithPlacementGroupSupport
            ) or not compute.is_suitable_placement_group(self.placement_group, offer):
                return False
        if (
            check_availability_zones
            and self.availability_zones is not None
            and (
                offer.availability_zones is None
                or not any(z.lower() in self.availability_zones for z in offer.availability_zones)
            )
        ):
            return False
        # Offer is futher filtered against volumes AZs in Compute implementation, see
        # ComputeWithCreateInstanceSupport._restrict_instance_offer_az_to_volumes_az()
        if (
            self.volumes_locations is not None
            and (offer.backend, offer.region.lower()) not in self.volumes_locations
            and (offer.backend, None) not in self.volumes_locations
        ):
            return False
        return True


def _filter_offers(
    offers: Iterable[Tuple[Backend, InstanceOfferWithAvailability]],
    offer_filter: _OfferFilter,
) -> Iterator[Tuple[Backend, InstanceOfferWithAvailability]]:
    for b, offer in offers:
        # Check AZs once while preparing the restricted offer below.
        if not offer_filter.matches(b, offer, check_availability_zones=False):
            continue
        if offer_filter.availability_zones is not None:
            if offer.availability_zones is None:
                continue
            new_offer = offer.model_copy()
            new_offer.availability_zones = [
                z for z in offer.availability_zones if z.lower() in offer_filter.availability_zones
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
        divisible, total_blocks = _get_offer_blocks(offer, blocks)
        if not divisible:
            continue
        new_offer = offer.model_copy()
        new_offer.total_blocks = total_blocks
        yield (backend, new_offer)


def _get_offer_blocks(
    offer: InstanceOfferWithAvailability, blocks: Union[int, Literal["auto"]]
) -> tuple[bool, int]:
    resources = offer.instance.resources
    gpu_count = len(resources.gpus)
    if gpu_count > 0 and resources.gpus[0].vendor == gpuhunt.AcceleratorVendor.GOOGLE:
        # TPUs cannot be shared
        gpu_count = 1
    return is_divisible_into_blocks(resources.cpus, gpu_count, blocks)
