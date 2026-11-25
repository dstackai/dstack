import itertools
from typing import Optional

import gpuhunt
import pytest

from dstack._internal.core.backends.base.offers import (
    OfferMatcher,
    offer_to_catalog_item,
    requirements_to_query_filter,
)
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import (
    Disk,
    Gpu,
    InstanceOffer,
    InstanceType,
    Resources,
)
from dstack._internal.core.models.resources import ResourcesSpec
from dstack._internal.core.models.runs import Requirements

NVIDIA = gpuhunt.AcceleratorVendor.NVIDIA
AMD = gpuhunt.AcceleratorVendor.AMD
GOOGLE = gpuhunt.AcceleratorVendor.GOOGLE

_GPU_CONFIGS: list[list[Gpu]] = [
    [],
    [Gpu(name="A100", memory_mib=40 * 1024, vendor=NVIDIA)],
    [Gpu(name="A100", memory_mib=80 * 1024, vendor=NVIDIA)] * 8,
    [Gpu(name="a100", memory_mib=80 * 1024, vendor=NVIDIA)] * 2,
    [Gpu(name="H100", memory_mib=80 * 1024, vendor=NVIDIA)] * 8,
    [Gpu(name="T4", memory_mib=16 * 1024, vendor=NVIDIA)],
    [Gpu(name="UnknownGPU", memory_mib=24 * 1024, vendor=NVIDIA)],
    [Gpu(name="MI300X", memory_mib=192 * 1024, vendor=AMD)] * 8,
    [Gpu(name="v5litepod-8", memory_mib=16 * 1024, vendor=GOOGLE)],
]


def _make_offers() -> list[InstanceOffer]:
    offers = []
    for spot, cpu_arch, cpus, memory_mib, gpus, disk_gib, price in itertools.product(
        [False, True],
        [None, gpuhunt.CPUArchitecture.X86, gpuhunt.CPUArchitecture.ARM],
        [1, 4, 96],
        [512, 16 * 1024, 1024 * 1024],
        _GPU_CONFIGS,
        [0, 50, 500],
        [0.5, 2.0],
    ):
        offers.append(
            InstanceOffer(
                backend=BackendType.AWS,
                instance=InstanceType(
                    name="test-instance",
                    resources=Resources(
                        cpus=cpus,
                        memory_mib=memory_mib,
                        gpus=gpus,
                        spot=spot,
                        disk=Disk(size_mib=disk_gib * 1024),
                        cpu_arch=cpu_arch,
                    ),
                ),
                region="test-region",
                price=price,
            )
        )
    return offers


_OFFERS = _make_offers()

_RESOURCES = [
    {},
    {"gpu": None},
    {"gpu": 0},
    {"gpu": "1.."},
    {"gpu": "..8"},
    {"gpu": "2..4"},
    {"gpu": "nvidia"},
    {"gpu": "nvidia:..8"},
    {"gpu": "nvidia:0.."},
    {"gpu": "amd"},
    {"gpu": "tpu"},
    {"gpu": "A100"},
    {"gpu": "a100:2.."},
    {"gpu": "A100,H100:8"},
    {"gpu": {"name": [], "count": "0.."}},
    {"gpu": {"name": [], "count": "..8"}},
    {"gpu": {"name": ["A100"], "count": "0.."}},
    {"gpu": "40GB.."},
    {"gpu": "24GB..80GB"},
    {"gpu": {"memory": "24GB..", "count": "0.."}},
    {"gpu": {"memory": "24GB..", "count": "..8"}},
    {"gpu": {"memory": "..16GB", "count": "..8"}},
    {"gpu": {"total_memory": "160GB.."}},
    {"gpu": {"total_memory": "..100GB", "count": "..8"}},
    {"gpu": {"total_memory": "1GB..", "count": "..8"}},
    {"gpu": {"compute_capability": "8.0"}},
    {"gpu": {"compute_capability": "9.0", "count": "0.."}},
    {"gpu": {"compute_capability": "7.5", "count": "..8"}},
    {"gpu": {"vendor": "nvidia", "name": ["A100"], "memory": "80GB", "count": 8}},
    {"cpu": "arm"},
    {"cpu": "x86:4.."},
    {"cpu": "..4"},
    {"cpu": "4..4"},
    {"memory": "0.5GB.."},
    {"memory": "..16GB"},
    {"memory": "1TB.."},
    {"disk": "100GB.."},
    {"disk": "..100GB"},
    {"disk": None},
    {"cpu": "..1", "memory": "..1GB", "gpu": 0, "disk": "..10GB"},
]

_REQUIREMENTS = [
    pytest.param(
        Requirements(
            resources=ResourcesSpec.model_validate(resources), spot=spot, max_price=price
        ),
        id=f"{resources}-spot={spot}-max_price={price}",
    )
    for resources, spot, price in itertools.chain(
        ((resources, None, None) for resources in _RESOURCES),
        (({}, spot, None) for spot in [True, False]),
        (({}, None, price) for price in [0.5, 1.0, 2.0]),
        (({"gpu": "A100"}, False, 1.0),),
    )
]


@pytest.mark.parametrize("requirements", _REQUIREMENTS)
@pytest.mark.parametrize("check_disk", [True, False])
def test_offer_matcher_matches_gpuhunt(requirements: Requirements, check_disk: bool):
    matcher = OfferMatcher(requirements, check_disk=check_disk)
    query_filter = requirements_to_query_filter(requirements, ignore_disk=not check_disk)
    mismatches: list[tuple[InstanceOffer, Optional[bool]]] = []
    for offer in _OFFERS:
        expected = gpuhunt.matches(offer_to_catalog_item(offer), q=query_filter)
        if matcher.matches(offer) != expected:
            mismatches.append((offer, expected))
    assert mismatches == []
