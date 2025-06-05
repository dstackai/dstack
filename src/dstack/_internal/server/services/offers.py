from typing import List, Literal, Optional, Tuple, Union

import gpuhunt

from dstack._internal.core.backends import (
    BACKENDS_WITH_CREATE_INSTANCE_SUPPORT,
    BACKENDS_WITH_MULTINODE_SUPPORT,
    BACKENDS_WITH_RESERVATION_SUPPORT,
)
from dstack._internal.core.backends.base.backend import Backend
from dstack._internal.core.backends.base.compute import ComputeWithPlacementGroupSupport
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
) -> List[Tuple[Backend, InstanceOfferWithAvailability]]:
    backends: List[Backend] = await backends_services.get_project_backends(project=project)

    # For backward-compatibility to show offers if users set `backends: [dstack]`
    if (
        profile.backends is not None
        and len(profile.backends) == 1
        and BackendType.DSTACK in profile.backends
    ):
        profile.backends = None

    backend_types = profile.backends
    regions = profile.regions
    availability_zones = profile.availability_zones

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

    if privileged or instance_mounts:
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

    offers = await backends_services.get_instance_offers(
        backends=backends,
        requirements=requirements,
        exclude_not_available=exclude_not_available,
    )

    # Filter offers again for backends since a backend
    # can return offers of different backend types (e.g. BackendType.DSTACK).
    # The first filter should remain as an optimization.
    if backend_types is not None:
        offers = [(b, o) for b, o in offers if o.backend in backend_types]

    if regions is not None:
        regions = [r.lower() for r in regions]
        offers = [(b, o) for b, o in offers if o.region.lower() in regions]

    if availability_zones is not None:
        new_offers = []
        for b, o in offers:
            if o.availability_zones is not None:
                new_offer = o.copy()
                new_offer.availability_zones = [
                    z for z in o.availability_zones if z in availability_zones
                ]
                if new_offer.availability_zones:
                    new_offers.append((b, new_offer))
        offers = new_offers

    if placement_group is not None:
        new_offers = []
        for b, o in offers:
            for backend in backends:
                compute = backend.compute()
                if isinstance(
                    compute, ComputeWithPlacementGroupSupport
                ) and compute.is_suitable_placement_group(placement_group, o):
                    new_offers.append((b, o))
                    break
        offers = new_offers

    if profile.instance_types is not None:
        instance_types = [i.lower() for i in profile.instance_types]
        offers = [(b, o) for b, o in offers if o.instance.name.lower() in instance_types]

    if blocks == 1:
        return offers

    shareable_offers = []
    for backend, offer in offers:
        resources = offer.instance.resources
        cpu_count = resources.cpus
        gpu_count = len(resources.gpus)
        if gpu_count > 0 and resources.gpus[0].vendor == gpuhunt.AcceleratorVendor.GOOGLE:
            # TPUs cannot be shared
            gpu_count = 1
        divisible, _blocks = is_divisible_into_blocks(cpu_count, gpu_count, blocks)
        if not divisible:
            continue
        offer.total_blocks = _blocks
        shareable_offers.append((backend, offer))
    return shareable_offers


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
        availability=offer.availability,
        blocks=blocks,
        total_blocks=total_blocks,
    )
