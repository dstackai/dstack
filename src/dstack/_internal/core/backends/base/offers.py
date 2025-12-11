from collections.abc import Iterable, Iterator
from dataclasses import asdict
from typing import Callable, List, Optional, TypeVar

import gpuhunt
from pydantic import parse_obj_as

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import (
    Disk,
    Gpu,
    InstanceOffer,
    InstanceOfferWithAvailability,
    InstanceType,
    Resources,
)
from dstack._internal.core.models.resources import DEFAULT_DISK, CPUSpec, Memory, Range
from dstack._internal.core.models.runs import Requirements
from dstack._internal.utils.common import get_or_error

# Offers not supported by all dstack versions are hidden behind one or more flags.
# This list enables the flags that are currently supported.
SUPPORTED_GPUHUNT_FLAGS = [
    "oci-spot",
    "lambda-arm",
    "gcp-a4",
    "gcp-g4",
    "gcp-dws-calendar-mode",
    "runpod-cluster",
]


def get_catalog_offers(
    backend: BackendType,
    locations: Optional[List[str]] = None,
    requirements: Optional[Requirements] = None,
    configurable_disk_size: Range[Memory] = Range[Memory](min=Memory.parse("1GB"), max=None),
    extra_filter: Optional[Callable[[InstanceOffer], bool]] = None,
    catalog: Optional[gpuhunt.Catalog] = None,
) -> List[InstanceOffer]:
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
    gpus = []
    if item.gpu_count > 0:
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
    resources = Resources(
        cpu_arch=item.cpu_arch,
        cpus=item.cpu,
        memory_mib=round(item.memory * 1024),
        gpus=gpus,
        spot=item.spot,
        disk=Disk(size_mib=disk_size_mib),
    )
    return InstanceOffer(
        backend=backend,
        instance=InstanceType(
            name=item.instance_name,
            resources=resources,
        ),
        region=item.location,
        price=item.price,
        backend_data=item.provider_data,
    )


def offer_to_catalog_item(offer: InstanceOffer) -> gpuhunt.CatalogItem:
    cpu_arch = offer.instance.resources.cpu_arch
    if cpu_arch is None:
        cpu_arch = gpuhunt.CPUArchitecture.X86
    gpu_count = len(offer.instance.resources.gpus)
    gpu_vendor = None
    gpu_name = None
    gpu_memory = None
    if gpu_count > 0:
        gpu = offer.instance.resources.gpus[0]
        gpu_vendor = gpu.vendor
        gpu_name = gpu.name
        gpu_memory = gpu.memory_mib / 1024
    return gpuhunt.CatalogItem(
        provider=offer.backend.value,
        instance_name=offer.instance.name,
        location=offer.region,
        price=offer.price,
        cpu_arch=cpu_arch,
        cpu=offer.instance.resources.cpus,
        memory=offer.instance.resources.memory_mib / 1024,
        gpu_count=gpu_count,
        gpu_vendor=gpu_vendor,
        gpu_name=gpu_name,
        gpu_memory=gpu_memory,
        spot=offer.instance.resources.spot,
        disk_size=offer.instance.resources.disk.size_mib / 1024,
    )


def requirements_to_query_filter(req: Optional[Requirements]) -> gpuhunt.QueryFilter:
    q = gpuhunt.QueryFilter(allowed_flags=SUPPORTED_GPUHUNT_FLAGS)
    if req is None:
        return q

    q.max_price = req.max_price
    q.spot = req.spot

    res = req.resources
    if res.cpu:
        # TODO: Remove in 0.20. Use res.cpu directly
        cpu = parse_obj_as(CPUSpec, res.cpu)
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


InstanceOfferT = TypeVar("InstanceOfferT", InstanceOffer, InstanceOfferWithAvailability)


def filter_offers_by_requirements(
    offers: Iterable[InstanceOfferT],
    requirements: Optional[Requirements],
) -> Iterator[InstanceOfferT]:
    query_filter = requirements_to_query_filter(requirements)
    for offer in offers:
        catalog_item = offer_to_catalog_item(offer)
        if gpuhunt.matches(catalog_item, q=query_filter):
            yield offer


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
        disk_size_gib = disk_size_range.min

    return round(disk_size_gib * 1024)


OfferModifier = Callable[[InstanceOfferWithAvailability], Optional[InstanceOfferWithAvailability]]


def get_offers_disk_modifier(
    configurable_disk_size: Range[Memory], requirements: Requirements
) -> OfferModifier:
    """
    Returns a func that modifies offers disk by setting min value that satisfies both
    `configurable_disk_size` and `requirements`.
    """

    def modifier(offer: InstanceOfferWithAvailability) -> Optional[InstanceOfferWithAvailability]:
        requirements_disk_range = DEFAULT_DISK.size
        if requirements.resources.disk is not None:
            requirements_disk_range = requirements.resources.disk.size
        disk_size_range = requirements_disk_range.intersect(configurable_disk_size)
        if disk_size_range is None:
            return None
        offer_copy = offer.copy(deep=True)
        offer_copy.instance.resources.disk = Disk(
            size_mib=get_or_error(disk_size_range.min) * 1024
        )
        offer_copy.instance.resources.update_description()
        return offer_copy

    return modifier
