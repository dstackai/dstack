from typing import Callable, List, Optional

import gpuhunt

from dstack._internal.core.models.instances import Gpu, InstanceOffer, InstanceType, Resources
from dstack._internal.core.models.runs import Requirements


def get_catalog_offers(
    provider: str,
    locations: Optional[List[str]] = None,
    requirements: Optional[Requirements] = None,
    extra_filter: Optional[Callable[[InstanceOffer], bool]] = None,
) -> List[InstanceOffer]:
    filters = dict(provider=[provider])
    if requirements is not None:
        filters.update(
            min_cpu=requirements.cpus,
            max_price=requirements.max_price,
            spot=requirements.spot,
        )
        if requirements.memory_mib is not None:
            filters["min_memory"] = requirements.memory_mib / 1024
        if requirements.gpus is not None:
            if requirements.gpus.name is not None:
                filters["gpu_name"] = [requirements.gpus.name]
            if requirements.gpus.memory_mib is not None:
                filters["min_gpu_memory"] = requirements.gpus.memory_mib / 1024
            if requirements.gpus.count is not None:
                filters["min_gpu_count"] = requirements.gpus.count
            if requirements.gpus.total_memory_mib is not None:
                filters["min_total_gpu_memory"] = requirements.gpus.total_memory_mib / 1024
            if requirements.gpus.compute_capability is not None:
                filters["min_compute_capability"] = requirements.gpus.compute_capability

    offers = []
    for item in gpuhunt.query(**filters):
        if locations is not None and item.location not in locations:
            continue
        offer = _catalog_item_to_offer(item)
        if extra_filter is not None and not extra_filter(offer):
            continue
        offers.append(offer)
    return offers


def _catalog_item_to_offer(item: gpuhunt.CatalogItem) -> InstanceOffer:
    gpus = []
    if item.gpu_count > 0:
        gpus = [Gpu(name=item.gpu_name, memory_mib=round(item.gpu_memory * 1024))] * item.gpu_count
    return InstanceOffer(
        instance=InstanceType(
            name=item.instance_name,
            resources=Resources(
                cpus=item.cpu,
                memory_mib=round(item.memory * 1024),
                gpus=gpus,
                spot=item.spot,
            ),
        ),
        region=item.location,
        price=item.price,
    )
