from unittest.mock import MagicMock, patch

from dstack._internal.core.backends.slurm.compute import SlurmCompute
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import (
    Disk,
    Gpu,
    InstanceAvailability,
    InstanceOfferWithAvailability,
    InstanceType,
    Resources,
)
from dstack._internal.core.models.resources import ResourcesSpec
from dstack._internal.core.models.runs import Requirements


def _compute() -> SlurmCompute:
    # Cluster discovery is mocked out, so the config itself is never inspected.
    with patch(
        "dstack._internal.core.backends.slurm.compute.get_clusters_from_backend_config",
        return_value=[],
    ):
        return SlurmCompute(MagicMock())


def _node_offer() -> InstanceOfferWithAvailability:
    return InstanceOfferWithAvailability(
        backend=BackendType.SLURM,
        instance=InstanceType(
            name="slurm-node",
            resources=Resources(
                cpus=16,
                memory_mib=128 * 1024,
                gpus=[Gpu(name="H100", memory_mib=80 * 1024) for _ in range(8)],
                spot=False,
                disk=Disk(size_mib=500 * 1024),
            ),
        ),
        region="cluster1",
        price=0.0,
        availability=InstanceAvailability.AVAILABLE,
        availability_zones=["partition1"],
    )


def test_get_offers_modifiers_are_skipped_with_full_offers():
    compute = _compute()
    requirements = Requirements(resources=ResourcesSpec(cpu="2", memory="8GB", gpu="1"))

    assert compute.get_offers_modifiers(requirements, full_offers=True) == []
    assert compute.get_offers_modifiers(requirements, full_offers=False) != []


def test_get_offers_with_full_offers_keeps_full_node_resources():
    compute = _compute()
    compute.get_all_offers_with_availability = MagicMock(return_value=[_node_offer()])
    # Open-ended requirements so the full node satisfies them without an upper bound.
    requirements = Requirements(
        resources=ResourcesSpec(cpu="2..", memory="8GB..", gpu="1..", disk="100GB..")
    )

    full_offers = list(compute.get_offers(requirements, full_offers=True))

    assert len(full_offers) == 1
    full_resources = full_offers[0].instance.resources
    assert full_resources.cpus == 16
    assert full_resources.memory_mib == 128 * 1024
    assert len(full_resources.gpus) == 8
    assert full_resources.disk.size_mib == 500 * 1024


def test_get_offers_without_full_offers_adjusts_to_requested_slice():
    compute = _compute()
    compute.get_all_offers_with_availability = MagicMock(return_value=[_node_offer()])
    compute._get_cluster = MagicMock()
    requirements = Requirements(
        resources=ResourcesSpec(cpu="2..", memory="8GB..", gpu="1..", disk="100GB..")
    )

    # Slicing needs cluster/partition lookups, which are otherwise backed by live cluster state.
    with patch(
        "dstack._internal.core.backends.slurm.compute._get_cluster_partitions",
        return_value={"partition1"},
    ):
        adjusted_offers = list(compute.get_offers(requirements, full_offers=False))

    assert len(adjusted_offers) == 1
    adjusted_resources = adjusted_offers[0].instance.resources
    assert adjusted_resources.cpus == 2
    assert adjusted_resources.memory_mib == 8 * 1024
    assert len(adjusted_resources.gpus) == 1
    assert adjusted_resources.disk.size_mib == 100 * 1024
    assert adjusted_offers[0].availability_zones == ["partition1"]
