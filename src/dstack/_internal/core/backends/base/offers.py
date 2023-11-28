from dataclasses import asdict
from typing import Callable, List, Optional

import gpuhunt

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import Gpu, InstanceOffer, InstanceType, Resources
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
        offer = catalog_item_to_offer(backend, item)
        if extra_filter is not None and not extra_filter(offer):
            continue
        offers.append(offer)
    return offers


def catalog_item_to_offer(backend: BackendType, item: gpuhunt.CatalogItem) -> InstanceOffer:
    gpus = []
    if item.gpu_count > 0:
        gpus = [Gpu(name=item.gpu_name, memory_mib=round(item.gpu_memory * 1024))] * item.gpu_count
    resources = Resources(
        cpus=item.cpu,
        memory_mib=round(item.memory * 1024),
        gpus=gpus,
        spot=item.spot,
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


def requirements_to_query_filter(req: Optional[Requirements]) -> gpuhunt.QueryFilter:
    q = gpuhunt.QueryFilter()
    if req is None:
        return q
    q.min_cpu = req.cpus
    q.max_price = req.max_price
    q.min_disk_size = 100  # TODO(egor-s): take from requirements
    q.spot = req.spot
    if req.memory_mib is not None:
        q.min_memory = req.memory_mib / 1024
    if req.gpus is not None:
        if req.gpus.name is not None:
            q.gpu_name = [req.gpus.name]
        if req.gpus.memory_mib is not None:
            q.min_gpu_memory = req.gpus.memory_mib / 1024
        if req.gpus.count is not None:
            q.min_gpu_count = req.gpus.count
        if req.gpus.total_memory_mib is not None:
            q.min_total_gpu_memory = req.gpus.total_memory_mib / 1024
        if req.gpus.compute_capability is not None:
            q.min_compute_capability = req.gpus.compute_capability
    return q
