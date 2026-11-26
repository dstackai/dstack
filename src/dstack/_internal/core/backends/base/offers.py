from abc import ABC, abstractmethod
from dataclasses import asdict
from typing import Callable, Generic, List, Literal, Optional, TypeVar
from uuid import UUID

import gpuhunt
from cachetools import TTLCache

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import (
    Disk,
    Gpu,
    InstanceOffer,
    InstanceOfferWithAvailability,
    InstanceType,
    Resources,
)
from dstack._internal.core.models.resources import DEFAULT_DISK, GPUSpec, Memory, Range
from dstack._internal.core.models.runs import Job, Requirements, Run
from dstack._internal.utils.common import get_or_error

# Offers not supported by all dstack versions are hidden behind one or more flags.
# This list enables the flags that are currently supported.
SUPPORTED_GPUHUNT_FLAGS = [
    "oci-spot",
    "lambda-arm",
    "gcp-a4",
    "gcp-g4",
    "gcp-dws-calendar-mode",
    "runpod-cpu",
    "runpod-cluster",
    "hotaisle-bm",
]


NVIDIA_GPU_NAME_TO_COMPUTE_CAPABILITY_MAP = {
    gpu_info.name.lower(): gpu_info.compute_capability for gpu_info in gpuhunt.KNOWN_NVIDIA_GPUS
}
"""
`NvidiaGPUInfo.name` in `KNOWN_NVIDIA_GPUS` is not unique -- there are multiple variants with
the same name but different amount of memory, but Compute Capability of the variants is always
the same, so it's safe to use 1:1 mapping.
"""


def get_catalog_offers(
    backend: BackendType,
    locations: Optional[List[str]] = None,
    requirements: Optional[Requirements] = None,
    configurable_disk_size: Range[Memory] = Range[Memory](min=Memory.parse("1GB"), max=None),
    extra_filter: Optional[Callable[[InstanceOffer], bool]] = None,
    catalog: Optional[gpuhunt.Catalog] = None,
    catalog_item_filter: Optional[Callable[[gpuhunt.CatalogItem], bool]] = None,
) -> List[InstanceOffer]:
    """
    Returns offers from the `gpuhunt` catalog for the given `backend`.

    Note: historically, `gpuhunt` was responsible for filtering offers by `requirements`.
    The same filtering is now also done in `dstack` by `OfferMatcher` to avoid converting offers to `gpuhunt` items.
    Double filtering is not on a hot path (offers from `gpuhunt` are cached),
    but we should eventually drop it to avoid keeping matching logic in sync.

    Args:
        configurable_disk_size: disk sizes the backend can provision. Used for catalog items
        without a fixed disk size: the offer's disk is set to the smallest size within both
        this range and the required range (`DEFAULT_DISK` if `requirements` don't specify disk).
        `min` must be set, since it is the lower bound when the required range has none.
        catalog_item_filter: applied to raw catalog items before the conversion to
        `InstanceOffer` models. Use it for filtering that can be done on raw catalog fields
        to avoid expensive model construction for items that will be discarded.
    """
    provider = backend.value
    if backend == BackendType.DATACRUNCH:
        provider = BackendType.VERDA.value  # Backward compatibility
    if backend == BackendType.LAMBDA:
        provider = "lambdalabs"
    if backend == BackendType.AMDDEVCLOUD:
        provider = "digitalocean"
    q = requirements_to_query_filter(requirements)
    q.provider = [provider]
    offers = []

    catalog = catalog if catalog is not None else gpuhunt.default_catalog()
    for item in catalog.query(**asdict(q)):
        if locations is not None and item.location not in locations:
            continue
        if catalog_item_filter is not None and not catalog_item_filter(item):
            continue
        offer = catalog_item_to_offer(backend, item, requirements, configurable_disk_size)
        if offer is None:
            continue
        if extra_filter is not None and not extra_filter(offer):
            continue
        offers.append(offer)
    return offers


def catalog_item_to_offer(
    backend: BackendType,
    item: gpuhunt.CatalogItem,
    requirements: Optional[Requirements],
    configurable_disk_size: Range[Memory],
) -> Optional[InstanceOffer]:
    # Gpu() keeps validation for vendor normalization.
    # The rest use construct() to skip redundant validation — data comes from already validated CatalogItem.
    gpus = []
    if item.gpu_count > 0:
        # gpuhunt requires GPU name and memory for items with GPUs
        assert item.gpu_name is not None and item.gpu_memory is not None
        gpu = Gpu(
            vendor=item.gpu_vendor, name=item.gpu_name, memory_mib=round(item.gpu_memory * 1024)
        )
        gpus = [gpu] * item.gpu_count
    disk_size_mib = choose_disk_size_mib(
        catalog_item_disk_size_gib=item.disk_size,
        requirements_disk_size=requirements.resources.disk.size
        if requirements and requirements.resources.disk
        else None,
        configurable_disk_size=configurable_disk_size,
    )
    if disk_size_mib is None:
        return None
    resources = Resources.model_construct(
        cpu_arch=item.cpu_arch,
        cpus=item.cpu,
        memory_mib=round(item.memory * 1024),
        gpus=gpus,
        spot=item.spot,
        disk=Disk.model_construct(size_mib=disk_size_mib),
    )
    return InstanceOffer.model_construct(
        backend=backend,
        instance=InstanceType.model_construct(
            name=item.instance_name,
            resources=resources,
        ),
        region=item.location,
        price=item.price,
        backend_data=item.provider_data,
    )


def requirements_to_query_filter(req: Optional[Requirements]) -> gpuhunt.QueryFilter:
    q = gpuhunt.QueryFilter(allowed_flags=SUPPORTED_GPUHUNT_FLAGS)
    if req is None:
        return q

    q.max_price = req.max_price
    q.spot = req.spot

    res = req.resources
    if res.cpu:
        cpu = res.cpu
        q.cpu_arch = cpu.arch
        q.min_cpu = cpu.count.min
        q.max_cpu = cpu.count.max
    if res.memory:
        q.min_memory = res.memory.min
        q.max_memory = res.memory.max
    if res.disk:
        q.min_disk_size = res.disk.size.min
        q.max_disk_size = res.disk.size.max

    if res.gpu:
        q.gpu_vendor = res.gpu.vendor
        q.gpu_name = res.gpu.name
        if res.gpu.memory:
            q.min_gpu_memory = res.gpu.memory.min
            q.max_gpu_memory = res.gpu.memory.max
        if res.gpu.count:
            q.min_gpu_count = res.gpu.count.min
            q.max_gpu_count = res.gpu.count.max
        if res.gpu.total_memory:
            q.min_total_gpu_memory = res.gpu.total_memory.min
            q.max_total_gpu_memory = res.gpu.total_memory.max
        if res.gpu.compute_capability:
            q.min_compute_capability = res.gpu.compute_capability

    return q


_Bounds = tuple[Optional[float], Optional[float]]
"""`(min, max)`, where `None` means unbounded."""


class OfferMatcher:
    """
    Matches offers against `requirements`.

    Create one per `requirements` and reuse it for all offers.

    GPU constraints are checked against the offer's first GPU. If the minimum required GPU
    count is 0, offers without GPUs match regardless of other GPU constraints. Otherwise, an
    offer without GPUs is treated as having no GPU vendor, name, or compute capability, and
    0 GPU memory, so e.g. `gpu: nvidia:..8` doesn't match it. The disk is not checked if
    the offer's disk size is unknown (`size_mib == 0`).
    """

    def __init__(self, requirements: Requirements, *, check_disk: bool = True) -> None:
        resources = requirements.resources
        self._max_price = requirements.max_price
        self._spot = requirements.spot
        self._cpu_arch = resources.cpu.arch
        self._cpu_bounds: _Bounds = (resources.cpu.count.min, resources.cpu.count.max)
        self._memory_mib_bounds = _get_mib_bounds(resources.memory)
        self._gpu_spec = resources.gpu
        self._total_gpu_memory_mib_bounds: _Bounds = (None, None)
        self._matches_no_gpus = True
        if self._gpu_spec is not None:
            self._total_gpu_memory_mib_bounds = _get_mib_bounds(self._gpu_spec.total_memory)
            self._matches_no_gpus = _gpu_spec_matches_no_gpus(self._gpu_spec)
        self._disk_mib_bounds: Optional[_Bounds] = None
        if check_disk and resources.disk is not None:
            self._disk_mib_bounds = _get_mib_bounds(resources.disk.size)

    def matches(self, offer: InstanceOffer) -> bool:
        resources = offer.instance.resources
        if self._max_price is not None and offer.price > self._max_price:
            return False
        if self._spot is not None and resources.spot != self._spot:
            return False
        if self._cpu_arch is not None:
            cpu_arch = resources.cpu_arch or gpuhunt.CPUArchitecture.X86
            if cpu_arch != self._cpu_arch:
                return False
        if not _is_within(resources.cpus, *self._cpu_bounds):
            return False
        if not _is_within(resources.memory_mib, *self._memory_mib_bounds):
            return False
        if not self._matches_gpus(resources.gpus):
            return False
        if self._disk_mib_bounds is not None and not _disk_size_fits(
            resources.disk.size_mib, *self._disk_mib_bounds
        ):
            return False
        return True

    def _matches_gpus(self, gpus: list[Gpu]) -> bool:
        gpu_spec = self._gpu_spec
        if gpu_spec is None:
            return True
        if not gpus:
            return self._matches_no_gpus
        if not _is_within(len(gpus), gpu_spec.count.min, gpu_spec.count.max):
            return False
        # Assumes all GPUs are the same. On hosts with mixed GPUs (e.g. SSH or Kubernetes),
        # the other GPUs are not checked and total memory is estimated from the first one.
        if not gpu_matches_gpu_spec(gpus[0], gpu_spec):
            return False
        return _is_within(len(gpus) * gpus[0].memory_mib, *self._total_gpu_memory_mib_bounds)


def gpu_matches_gpu_spec(gpu: Gpu, gpu_spec: GPUSpec) -> bool:
    if gpu_spec.vendor is not None and gpu.vendor != gpu_spec.vendor:
        return False
    if gpu_spec.name is not None and gpu.name.lower() not in map(str.lower, gpu_spec.name):
        return False
    if gpu_spec.memory is not None:
        min_memory_gib = gpu_spec.memory.min
        if min_memory_gib is not None and gpu.memory_mib < min_memory_gib * 1024:
            return False
        max_memory_gib = gpu_spec.memory.max
        if max_memory_gib is not None and gpu.memory_mib > max_memory_gib * 1024:
            return False
    if gpu_spec.compute_capability is not None:
        if gpu.vendor != gpuhunt.AcceleratorVendor.NVIDIA:
            return False
        compute_capability = NVIDIA_GPU_NAME_TO_COMPUTE_CAPABILITY_MAP.get(gpu.name.lower())
        if compute_capability is None:
            return False
        if compute_capability < gpu_spec.compute_capability:
            return False
    return True


def _gpu_spec_matches_no_gpus(gpu_spec: GPUSpec) -> bool:
    if gpu_spec.count.min == 0:
        return True
    return (
        _is_within(0, gpu_spec.count.min, gpu_spec.count.max)
        and gpu_spec.vendor is None
        and gpu_spec.name is None
        and gpu_spec.compute_capability is None
        and _is_within(0, *_get_mib_bounds(gpu_spec.memory))
        and _is_within(0, *_get_mib_bounds(gpu_spec.total_memory))
    )


def _get_mib_bounds(memory_range: Optional[Range[Memory]]) -> _Bounds:
    if memory_range is None:
        return None, None
    min_mib = memory_range.min * 1024 if memory_range.min is not None else None
    max_mib = memory_range.max * 1024 if memory_range.max is not None else None
    return min_mib, max_mib


def _disk_size_fits(
    disk_size_mib: int, min_mib: Optional[float], max_mib: Optional[float]
) -> bool:
    if disk_size_mib == 0:
        # Unknown disk size
        return True
    return _is_within(disk_size_mib, min_mib, max_mib)


def _is_within(value: float, min_value: Optional[float], max_value: Optional[float]) -> bool:
    if min_value is not None and value < min_value:
        return False
    if max_value is not None and value > max_value:
        return False
    return True


def choose_disk_size_mib(
    catalog_item_disk_size_gib: Optional[float],
    requirements_disk_size: Optional[Range[Memory]],
    configurable_disk_size: Range[Memory],
) -> Optional[int]:
    if catalog_item_disk_size_gib:
        disk_size_gib = catalog_item_disk_size_gib
    else:
        disk_size_range = requirements_disk_size or DEFAULT_DISK.size
        disk_size_range = disk_size_range.intersect(configurable_disk_size)
        if disk_size_range is None:
            return None
        disk_size_gib = get_or_error(disk_size_range.min)

    return round(disk_size_gib * 1024)


OfferModifier = Callable[[InstanceOfferWithAvailability], Optional[InstanceOfferWithAvailability]]


class OfferDiskFitter:
    """
    Fits offers' disks to the `requirements` disk.

    Create one per `requirements` and reuse it for all offers: the fitted disk is computed
    once per distinct configurable disk size range and shared by all offers it is set on.
    """

    def __init__(self, requirements: Requirements) -> None:
        disk_spec = requirements.resources.disk
        self._fixed_disk_mib_bounds = (
            _get_mib_bounds(disk_spec.size) if disk_spec is not None else None
        )
        """The bounds fixed disks are checked against, `None` if fixed disks are not checked."""
        self._target_disk_range = disk_spec.size if disk_spec is not None else DEFAULT_DISK.size
        """The range configurable disks are fitted to."""
        self._disk_by_range: dict[tuple[Optional[float], Optional[float]], Optional[Disk]] = {}

    def fit(
        self,
        offer: InstanceOfferWithAvailability,
        configurable_disk_size: Optional[Range[Memory]],
    ) -> Optional[InstanceOfferWithAvailability]:
        """
        Returns the offer with the fitted disk, or `None` if the offer doesn't fit.

        If `configurable_disk_size` is `None`, the offer's disk is fixed and is only checked
        against `requirements`, the same way `OfferMatcher` checks it.
        Otherwise, the disk is set to the smallest size within both `configurable_disk_size`
        and the required range (`DEFAULT_DISK` if `requirements` don't specify disk).

        Never modifies `offer`. A changed offer shares all objects with `offer` except those on
        the path to the disk.
        """
        disk_size_mib = offer.instance.resources.disk.size_mib
        if configurable_disk_size is None:
            if self._fixed_disk_fits(disk_size_mib):
                return offer
            return None
        disk = self._get_disk(configurable_disk_size)
        if disk is None:
            return None
        if disk.size_mib == disk_size_mib:
            return offer
        resources = offer.instance.resources.model_copy(update={"disk": disk})
        instance = offer.instance.model_copy(update={"resources": resources})
        return offer.model_copy(update={"instance": instance})

    def _fixed_disk_fits(self, disk_size_mib: int) -> bool:
        if self._fixed_disk_mib_bounds is None:
            return True
        return _disk_size_fits(disk_size_mib, *self._fixed_disk_mib_bounds)

    def _get_disk(self, configurable_disk_size: Range[Memory]) -> Optional[Disk]:
        key = (configurable_disk_size.min, configurable_disk_size.max)
        if key not in self._disk_by_range:
            disk_size_range = self._target_disk_range.intersect(configurable_disk_size)
            disk = None
            if disk_size_range is not None:
                disk = Disk(size_mib=round(get_or_error(disk_size_range.min) * 1024))
            self._disk_by_range[key] = disk
        return self._disk_by_range[key]


OfferKeyT = TypeVar("OfferKeyT")


class BaseSkipOfferCache(Generic[OfferKeyT], ABC):
    """
    A base class for a cache to track (run/job, offer) pairs that failed to provision.

    Implementations can be used to skip offers based on, e.g., a region, an instance type,
    a region/type pair, etc.

    Subclasses must implement `_build_key()`.
    """

    def __init__(self, *, ttl: int, maxsize: int = 1000) -> None:
        self._cache = TTLCache[OfferKeyT, Literal[True]](maxsize=maxsize, ttl=ttl)

    def add(self, run: Run, job: Job, offer: InstanceOffer) -> None:
        self._cache[self._build_key(run, job, offer)] = True

    def check(self, run: Run, job: Job, offer: InstanceOffer) -> bool:
        return self._build_key(run, job, offer) in self._cache

    @abstractmethod
    def _build_key(self, run: Run, job: Job, offer: InstanceOffer) -> OfferKeyT:
        pass


class RegionalSkipOfferCache(BaseSkipOfferCache[tuple[UUID, str]]):
    """
    `RegionalSkipOfferRegionCache` tracks failed provisioning attempts based on the offer's region.

    The current implementation tracks _any_ job of the specific run (identified by `Run.id`)
    in the specific region (identified by `InstanceOffer.region`).
    """

    def _build_key(self, run: Run, job: Job, offer: InstanceOffer) -> tuple[UUID, str]:
        # The current implementation uses only Run.id ignoring the job/job spec.
        # A more sophisticated implementation could use some parts of the job spec
        # (e.g., requirements, volumes) instead.
        return (run.id, offer.region)
