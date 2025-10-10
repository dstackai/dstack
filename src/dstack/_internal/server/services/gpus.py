from typing import Dict, List, Literal, Optional, Tuple

from dstack._internal.core.backends.base.backend import Backend
from dstack._internal.core.errors import ServerClientError
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import InstanceOfferWithAvailability
from dstack._internal.core.models.profiles import SpotPolicy
from dstack._internal.core.models.resources import Range
from dstack._internal.core.models.runs import Requirements, RunSpec, get_policy_map
from dstack._internal.server.models import ProjectModel
from dstack._internal.server.schemas.gpus import (
    BackendGpu,
    BackendGpus,
    GpuGroup,
    ListGpusResponse,
)
from dstack._internal.server.services.offers import get_offers_by_requirements
from dstack._internal.utils.common import get_or_error


async def list_gpus_grouped(
    project: ProjectModel,
    run_spec: RunSpec,
    group_by: Optional[List[Literal["backend", "region", "count"]]] = None,
) -> ListGpusResponse:
    """Retrieves available GPU specifications based on a run spec, with optional grouping."""
    offers = await _get_gpu_offers(project=project, run_spec=run_spec)
    backend_gpus = _process_offers_into_backend_gpus(offers)
    group_by_set = set(group_by) if group_by else set()
    if "region" in group_by_set and "backend" not in group_by_set:
        raise ServerClientError("Cannot group by 'region' without also grouping by 'backend'")

    # Determine grouping strategy based on combination
    has_backend = "backend" in group_by_set
    has_region = "region" in group_by_set
    has_count = "count" in group_by_set
    if has_backend and has_region and has_count:
        gpus = _get_gpus_grouped_by_backend_region_and_count(backend_gpus)
    elif has_backend and has_count:
        gpus = _get_gpus_grouped_by_backend_and_count(backend_gpus)
    elif has_backend and has_region:
        gpus = _get_gpus_grouped_by_backend_and_region(backend_gpus)
    elif has_backend:
        gpus = _get_gpus_grouped_by_backend(backend_gpus)
    elif has_count:
        gpus = _get_gpus_grouped_by_count(backend_gpus)
    else:
        gpus = _get_gpus_with_no_grouping(backend_gpus)

    return ListGpusResponse(gpus=gpus)


async def _get_gpu_offers(
    project: ProjectModel, run_spec: RunSpec
) -> List[Tuple[Backend, InstanceOfferWithAvailability]]:
    """Fetches all available instance offers that match the run spec's GPU requirements."""
    profile = run_spec.merged_profile
    requirements = Requirements(
        resources=run_spec.configuration.resources,
        max_price=profile.max_price,
        spot=get_policy_map(profile.spot_policy, default=SpotPolicy.AUTO),
        reservation=profile.reservation,
    )
    return await get_offers_by_requirements(
        project=project,
        profile=profile,
        requirements=requirements,
        exclude_not_available=False,
        multinode=False,
        volumes=None,
        privileged=False,
        instance_mounts=False,
    )


def _process_offers_into_backend_gpus(
    offers: List[Tuple[Backend, InstanceOfferWithAvailability]],
) -> List[BackendGpus]:
    """Transforms raw offers into a structured list of BackendGpus, aggregating GPU info."""
    backend_data: Dict[BackendType, Dict] = {}

    for _, offer in offers:
        backend_type = offer.backend
        if backend_type not in backend_data:
            backend_data[backend_type] = {"gpus": {}, "regions": set()}

        backend_data[backend_type]["regions"].add(offer.region)

        if not offer.instance.resources.gpus:
            continue

        gpu_types_in_offer = {}
        for gpu in offer.instance.resources.gpus:
            gpu_type_key = (gpu.name, gpu.memory_mib, gpu.vendor)
            if gpu_type_key not in gpu_types_in_offer:
                gpu_types_in_offer[gpu_type_key] = 0
            gpu_types_in_offer[gpu_type_key] += 1

        for (
            gpu_name,
            gpu_memory_mib,
            gpu_vendor,
        ), gpu_count_in_offer in gpu_types_in_offer.items():
            instance_config_key = (
                gpu_name,
                gpu_memory_mib,
                gpu_vendor,
                gpu_count_in_offer,
                offer.instance.resources.spot,
                offer.region,
            )

            if instance_config_key not in backend_data[backend_type]["gpus"]:
                backend_data[backend_type]["gpus"][instance_config_key] = BackendGpu(
                    name=gpu_name,
                    memory_mib=gpu_memory_mib,
                    vendor=gpu_vendor,
                    availability=offer.availability,
                    spot=offer.instance.resources.spot,
                    count=gpu_count_in_offer,
                    price=offer.price,
                    region=offer.region,
                )

    backend_gpus_list = []
    for backend_type, data in backend_data.items():
        gpus_list = sorted(
            list(data["gpus"].values()),
            key=lambda g: (
                not g.availability.is_available(),
                g.vendor.value,
                g.name,
                g.memory_mib,
            ),
        )
        backend_gpus_list.append(
            BackendGpus(
                backend_type=backend_type,
                gpus=gpus_list,
                regions=sorted(list(data["regions"])),
            )
        )
    return backend_gpus_list


def _update_gpu_group(row: GpuGroup, gpu: BackendGpu, backend_type: BackendType):
    """Updates an existing GpuGroup with new data from another GPU offer."""
    spot_type: Literal["spot", "on-demand"] = "spot" if gpu.spot else "on-demand"

    if gpu.availability not in row.availability:
        row.availability.append(gpu.availability)
    if spot_type not in row.spot:
        row.spot.append(spot_type)
    if row.backends and backend_type not in row.backends:
        row.backends.append(backend_type)

    # FIXME: Consider using non-optional range
    assert row.count.min is not None
    assert row.count.max is not None
    assert row.price.min is not None
    assert row.price.max is not None

    row.count.min = min(row.count.min, gpu.count)
    row.count.max = max(row.count.max, gpu.count)
    per_gpu_price = gpu.price / gpu.count
    row.price.min = min(row.price.min, per_gpu_price)
    row.price.max = max(row.price.max, per_gpu_price)


def _get_gpus_with_no_grouping(backend_gpus: List[BackendGpus]) -> List[GpuGroup]:
    """Aggregates GPU specs into a flat list, without any grouping."""
    gpu_rows: Dict[Tuple, GpuGroup] = {}
    for backend in backend_gpus:
        for gpu in backend.gpus:
            key = (gpu.name, gpu.memory_mib, gpu.vendor)
            if key not in gpu_rows:
                per_gpu_price = gpu.price / gpu.count
                price_range = Range[float](min=per_gpu_price, max=per_gpu_price)

                gpu_rows[key] = GpuGroup(
                    name=gpu.name,
                    memory_mib=gpu.memory_mib,
                    vendor=gpu.vendor,
                    availability=[gpu.availability],
                    spot=["spot" if gpu.spot else "on-demand"],
                    count=Range[int](min=gpu.count, max=gpu.count),
                    price=price_range,
                    backends=[backend.backend_type],
                )
            else:
                _update_gpu_group(gpu_rows[key], gpu, backend.backend_type)

    result = sorted(
        list(gpu_rows.values()),
        key=lambda g: (
            not any(av.is_available() for av in g.availability),
            g.price.min,
            g.price.max,
            g.name,
            g.memory_mib,
        ),
    )

    return result


def _get_gpus_grouped_by_backend(backend_gpus: List[BackendGpus]) -> List[GpuGroup]:
    """Aggregates GPU specs, grouping them by backend."""
    gpu_rows: Dict[Tuple, GpuGroup] = {}
    for backend in backend_gpus:
        for gpu in backend.gpus:
            key = (gpu.name, gpu.memory_mib, gpu.vendor, backend.backend_type)
            if key not in gpu_rows:
                per_gpu_price = gpu.price / gpu.count
                gpu_rows[key] = GpuGroup(
                    name=gpu.name,
                    memory_mib=gpu.memory_mib,
                    vendor=gpu.vendor,
                    availability=[gpu.availability],
                    spot=["spot" if gpu.spot else "on-demand"],
                    count=Range[int](min=gpu.count, max=gpu.count),
                    price=Range[float](min=per_gpu_price, max=per_gpu_price),
                    backend=backend.backend_type,
                    regions=backend.regions.copy(),
                )
            else:
                _update_gpu_group(gpu_rows[key], gpu, backend.backend_type)

    return sorted(
        list(gpu_rows.values()),
        key=lambda g: (
            not any(av.is_available() for av in g.availability),
            g.price.min,
            g.price.max,
            get_or_error(g.backend).value,
            g.name,
            g.memory_mib,
        ),
    )


def _get_gpus_grouped_by_backend_and_region(backend_gpus: List[BackendGpus]) -> List[GpuGroup]:
    """Aggregates GPU specs, grouping them by both backend and region."""
    gpu_rows: Dict[Tuple, GpuGroup] = {}
    for backend in backend_gpus:
        for gpu in backend.gpus:
            key = (gpu.name, gpu.memory_mib, gpu.vendor, backend.backend_type, gpu.region)
            if key not in gpu_rows:
                per_gpu_price = gpu.price / gpu.count
                gpu_rows[key] = GpuGroup(
                    name=gpu.name,
                    memory_mib=gpu.memory_mib,
                    vendor=gpu.vendor,
                    availability=[gpu.availability],
                    spot=["spot" if gpu.spot else "on-demand"],
                    count=Range[int](min=gpu.count, max=gpu.count),
                    price=Range[float](min=per_gpu_price, max=per_gpu_price),
                    backend=backend.backend_type,
                    region=gpu.region,
                )
            else:
                _update_gpu_group(gpu_rows[key], gpu, backend.backend_type)

    return sorted(
        list(gpu_rows.values()),
        key=lambda g: (
            not any(av.is_available() for av in g.availability),
            g.price.min,
            g.price.max,
            get_or_error(g.backend).value,
            g.region,
            g.name,
            g.memory_mib,
        ),
    )


def _get_gpus_grouped_by_count(backend_gpus: List[BackendGpus]) -> List[GpuGroup]:
    """Aggregates GPU specs, grouping them by GPU count."""
    gpu_rows: Dict[Tuple, GpuGroup] = {}
    for backend in backend_gpus:
        for gpu in backend.gpus:
            key = (gpu.name, gpu.memory_mib, gpu.vendor, gpu.count)
            if key not in gpu_rows:
                per_gpu_price = gpu.price / gpu.count
                gpu_rows[key] = GpuGroup(
                    name=gpu.name,
                    memory_mib=gpu.memory_mib,
                    vendor=gpu.vendor,
                    availability=[gpu.availability],
                    spot=["spot" if gpu.spot else "on-demand"],
                    count=Range[int](min=gpu.count, max=gpu.count),
                    price=Range[float](min=per_gpu_price, max=per_gpu_price),
                    backends=[backend.backend_type],
                )
            else:
                _update_gpu_group(gpu_rows[key], gpu, backend.backend_type)

    return sorted(
        list(gpu_rows.values()),
        key=lambda g: (
            not any(av.is_available() for av in g.availability),
            g.price.min,
            g.price.max,
            g.count.min,
            g.name,
            g.memory_mib,
        ),
    )


def _get_gpus_grouped_by_backend_and_count(backend_gpus: List[BackendGpus]) -> List[GpuGroup]:
    """Aggregates GPU specs, grouping them by backend and GPU count."""
    gpu_rows: Dict[Tuple, GpuGroup] = {}
    for backend in backend_gpus:
        for gpu in backend.gpus:
            key = (gpu.name, gpu.memory_mib, gpu.vendor, backend.backend_type, gpu.count)
            if key not in gpu_rows:
                per_gpu_price = gpu.price / gpu.count
                gpu_rows[key] = GpuGroup(
                    name=gpu.name,
                    memory_mib=gpu.memory_mib,
                    vendor=gpu.vendor,
                    availability=[gpu.availability],
                    spot=["spot" if gpu.spot else "on-demand"],
                    count=Range[int](min=gpu.count, max=gpu.count),
                    price=Range[float](min=per_gpu_price, max=per_gpu_price),
                    backend=backend.backend_type,
                    regions=backend.regions.copy(),
                )
            else:
                _update_gpu_group(gpu_rows[key], gpu, backend.backend_type)

    return sorted(
        list(gpu_rows.values()),
        key=lambda g: (
            not any(av.is_available() for av in g.availability),
            g.price.min,
            g.price.max,
            get_or_error(g.backend).value,
            g.count.min,
            g.name,
            g.memory_mib,
        ),
    )


def _get_gpus_grouped_by_backend_region_and_count(
    backend_gpus: List[BackendGpus],
) -> List[GpuGroup]:
    """Aggregates GPU specs, grouping them by backend, region, and GPU count."""
    gpu_rows: Dict[Tuple, GpuGroup] = {}
    for backend in backend_gpus:
        for gpu in backend.gpus:
            key = (
                gpu.name,
                gpu.memory_mib,
                gpu.vendor,
                backend.backend_type,
                gpu.region,
                gpu.count,
            )
            if key not in gpu_rows:
                per_gpu_price = gpu.price / gpu.count
                gpu_rows[key] = GpuGroup(
                    name=gpu.name,
                    memory_mib=gpu.memory_mib,
                    vendor=gpu.vendor,
                    availability=[gpu.availability],
                    spot=["spot" if gpu.spot else "on-demand"],
                    count=Range[int](min=gpu.count, max=gpu.count),
                    price=Range[float](min=per_gpu_price, max=per_gpu_price),
                    backend=backend.backend_type,
                    region=gpu.region,
                )
            else:
                _update_gpu_group(gpu_rows[key], gpu, backend.backend_type)

    return sorted(
        list(gpu_rows.values()),
        key=lambda g: (
            not any(av.is_available() for av in g.availability),
            g.price.min,
            g.price.max,
            get_or_error(g.backend).value,
            g.region,
            g.count.min,
            g.name,
            g.memory_mib,
        ),
    )
