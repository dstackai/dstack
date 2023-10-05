from typing import Callable, List, Optional, Set

from dstack._internal.core.backends.base import catalog
from dstack._internal.core.backends.base.catalog import (  # TODO replace with gpuhunt.CatalogItem
    CatalogItem,
)
from dstack._internal.core.models.instances import Gpu, InstanceOffer, InstanceType, Resources
from dstack._internal.core.models.runs import Requirements


def get_catalog_offers(
    provider: str,
    locations: Optional[List[str]] = None,
    requirements: Optional[Requirements] = None,
    extra_filter: Optional[Callable[[InstanceOffer], bool]] = None,
) -> List[InstanceOffer]:
    offers = []
    for item in catalog.query(provider=provider):
        if locations is not None and item.location not in locations:
            continue
        offer = _catalog_item_to_offer(item)
        if not _satisfies_requirements(offer, requirements):
            continue
        if extra_filter is not None and not extra_filter(offer):
            continue
        offers.append(offer)
    return offers


def _catalog_item_to_offer(item: CatalogItem) -> InstanceOffer:
    gpus = []
    if item.gpu_count > 0:
        gpus = [Gpu(name=item.gpu_name, memory_mib=round(item.gpu_memory * 1024))] * item.gpu_count
    return InstanceOffer(
        instance=InstanceType(
            name=item.instance_name,
            resources=Resources(
                cpus=item.cpus,
                memory_mib=round(item.memory * 1024),
                gpus=gpus,
                spot=item.spot,
            ),
        ),
        region=item.location,
        price=item.price,
    )


def _satisfies_requirements(offer: InstanceOffer, req: Optional[Requirements]) -> bool:
    res = offer.instance.resources
    if req is None:
        return True
    if req.max_price is not None and offer.price > req.max_price:
        return False
    if req.cpus is not None and res.cpus < req.cpus:
        return False
    if req.memory_mib is not None and res.memory_mib < req.memory_mib:
        return False
    if req.spot is not None and res.spot != req.spot:
        return False
    # todo shm_size_mib
    if req.gpus is not None:
        if len(res.gpus) < req.gpus.count:
            return False
        gpu = res.gpus[0]
        if req.gpus.name is not None and gpu.name != req.gpus.name:
            return False
        if req.gpus.memory_mib is not None and gpu.memory_mib < req.gpus.memory_mib:
            return False
    return True
