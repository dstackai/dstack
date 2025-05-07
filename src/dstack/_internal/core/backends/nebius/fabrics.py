from collections.abc import Container
from dataclasses import dataclass
from typing import Optional

from dstack._internal.core.models.instances import InstanceOffer


@dataclass(frozen=True)
class InfinibandFabric:
    name: str
    platform: str
    region: str


# https://docs.nebius.com/compute/clusters/gpu#fabrics
INFINIBAND_FABRICS = [
    InfinibandFabric("fabric-2", "gpu-h100-sxm", "eu-north1"),
    InfinibandFabric("fabric-3", "gpu-h100-sxm", "eu-north1"),
    InfinibandFabric("fabric-4", "gpu-h100-sxm", "eu-north1"),
    InfinibandFabric("fabric-5", "gpu-h200-sxm", "eu-west1"),
    InfinibandFabric("fabric-6", "gpu-h100-sxm", "eu-north1"),
    InfinibandFabric("fabric-7", "gpu-h200-sxm", "eu-north1"),
]


def get_suitable_infiniband_fabrics(
    offer: InstanceOffer, allowed_fabrics: Optional[Container[str]]
) -> list[str]:
    if len(offer.instance.resources.gpus) < 8:
        # From the create VM page in the Nebius Console:
        # > Only virtual machines with at least 8 NVIDIA® Hopper® H100 or H200 GPUs
        # > can be added to the cluster
        return []
    platform, _ = offer.instance.name.split()
    return [
        f.name
        for f in INFINIBAND_FABRICS
        if (
            f.platform == platform
            and f.region == offer.region
            and (allowed_fabrics is None or f.name in allowed_fabrics)
        )
    ]


def get_all_infiniband_fabrics() -> set[str]:
    return {f.name for f in INFINIBAND_FABRICS}
