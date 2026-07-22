from unittest.mock import MagicMock, patch

from dstack._internal.core.backends.kubernetes.compute import KubernetesCompute
from dstack._internal.core.backends.kubernetes.models import KubeconfigConfig, KubernetesConfig
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


def _compute() -> KubernetesCompute:
    with patch(
        "dstack._internal.core.backends.kubernetes.compute.get_clusters_from_backend_config",
        return_value=[],
    ):
        return KubernetesCompute(
            KubernetesConfig(
                kubeconfig=KubeconfigConfig(data="mocked", filename="-"),
                contexts=["ctx"],
            )
        )


def _node_offer() -> InstanceOfferWithAvailability:
    return InstanceOfferWithAvailability(
        backend=BackendType.KUBERNETES,
        instance=InstanceType(
            name="ctx-node",
            resources=Resources(
                cpus=8,
                memory_mib=64 * 1024,
                gpus=[Gpu(name="A100", memory_mib=80 * 1024) for _ in range(4)],
                spot=False,
                disk=Disk(size_mib=200 * 1024),
            ),
        ),
        region="ctx",
        price=0.0,
        availability=InstanceAvailability.AVAILABLE,
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
    assert full_resources.cpus == 8
    assert full_resources.memory_mib == 64 * 1024
    assert len(full_resources.gpus) == 4
    assert full_resources.disk.size_mib == 200 * 1024


def test_get_offers_without_full_offers_adjusts_to_requested_slice():
    compute = _compute()
    compute.get_all_offers_with_availability = MagicMock(return_value=[_node_offer()])
    requirements = Requirements(
        resources=ResourcesSpec(cpu="2..", memory="8GB..", gpu="1..", disk="100GB..")
    )

    adjusted_offers = list(compute.get_offers(requirements, full_offers=False))

    assert len(adjusted_offers) == 1
    adjusted_resources = adjusted_offers[0].instance.resources
    assert adjusted_resources.cpus == 2
    assert adjusted_resources.memory_mib == 8 * 1024
    assert len(adjusted_resources.gpus) == 1
    assert adjusted_resources.disk.size_mib == 100 * 1024
