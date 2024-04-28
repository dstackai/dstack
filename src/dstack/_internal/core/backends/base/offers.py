from dataclasses import asdict
from typing import Callable, List, Optional

import gpuhunt

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import (
    Disk,
    Gpu,
    InstanceOffer,
    InstanceType,
    Resources,
)
from dstack._internal.core.models.runs import Requirements


def get_catalog_offers(
    backend: BackendType,
    locations: Optional[List[str]] = None,
    requirements: Optional[Requirements] = None,
    extra_filter: Optional[Callable[[InstanceOffer], bool]] = None,
    catalog: Optional[gpuhunt.Catalog] = None,
) -> List[InstanceOffer]:
    provider = backend.value
    if backend == BackendType.LAMBDA:
        provider = "lambdalabs"
    q = requirements_to_query_filter(requirements)
    q.provider = [provider]
    offers = []

    catalog = catalog if catalog is not None else gpuhunt.default_catalog()
    for item in catalog.query(**asdict(q)):
        if locations is not None and item.location not in locations:
            continue
        offer = catalog_item_to_offer(backend, item, requirements)
        if extra_filter is not None and not extra_filter(offer):
            continue
        offers.append(offer)
    return offers


def catalog_item_to_offer(
    backend: BackendType, item: gpuhunt.CatalogItem, requirements: Optional[Requirements]
) -> InstanceOffer:
    gpus = []
    if item.gpu_count > 0:
        gpus = [Gpu(name=item.gpu_name, memory_mib=round(item.gpu_memory * 1024))] * item.gpu_count
    disk_size_mib = round(
        item.disk_size * 1024
        if item.disk_size
        else requirements.resources.disk.size.min * 1024
        if requirements and requirements.resources.disk
        else 102400  # TODO: Make requirements' fields required
    )
    resources = Resources(
        cpus=item.cpu,
        memory_mib=round(item.memory * 1024),
        gpus=gpus,
        spot=item.spot,
        disk=Disk(size_mib=disk_size_mib),
    )
    resources.description = resources.pretty_format()
    return InstanceOffer(
        backend=backend,
        instance=InstanceType(
            name=item.instance_name,
            resources=resources,
        ),
        region=item.location,
        price=item.price,
    )


def offer_to_catalog_item(offer: InstanceOffer) -> gpuhunt.CatalogItem:
    gpu_count = len(offer.instance.resources.gpus)
    gpu_name = None
    gpu_memory = None
    if gpu_count > 0:
        gpu = offer.instance.resources.gpus[0]
        gpu_name = gpu.name
        gpu_memory = gpu.memory_mib / 1024
    return gpuhunt.CatalogItem(
        provider=offer.backend.value,
        instance_name=offer.instance.name,
        location=offer.region,
        price=offer.price,
        cpu=offer.instance.resources.cpus,
        memory=offer.instance.resources.memory_mib / 1024,
        gpu_count=gpu_count,
        gpu_name=gpu_name,
        gpu_memory=gpu_memory,
        spot=offer.instance.resources.spot,
        disk_size=offer.instance.resources.disk.size_mib,
    )


def requirements_to_query_filter(req: Optional[Requirements]) -> gpuhunt.QueryFilter:
    q = gpuhunt.QueryFilter()
    if req is None:
        return q

    q.max_price = req.max_price
    q.spot = req.spot

    res = req.resources
    if res.cpu:
        q.min_cpu = res.cpu.min
        q.max_cpu = res.cpu.max
    if res.memory:
        q.min_memory = res.memory.min
        q.max_memory = res.memory.max
    if res.disk:
        q.min_disk_size = res.disk.size.min
        q.max_disk_size = res.disk.size.max

    if res.gpu:
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


def match_requirements(
    offers: List[InstanceOffer], requirements: Optional[Requirements]
) -> List[InstanceOffer]:
    query_filter = requirements_to_query_filter(requirements)
    filtered_offers = []
    for offer in offers:
        catalog_item = offer_to_catalog_item(offer)
        if gpuhunt.matches(catalog_item, q=query_filter):
            filtered_offers.append(offer)
    return filtered_offers
