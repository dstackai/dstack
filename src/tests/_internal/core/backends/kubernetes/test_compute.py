from unittest.mock import MagicMock, patch

import pytest
from kubernetes.client import V1Node, V1NodeSpec, V1NodeStatus, V1ObjectMeta

from dstack._internal.core.backends.kubernetes.compute import (
    KubernetesCompute,
    _get_nvidia_gpu_node_affinity,
)
from dstack._internal.core.backends.kubernetes.models import KubeconfigConfig, KubernetesConfig
from dstack._internal.core.backends.kubernetes.resources import get_instance_offer_from_node
from dstack._internal.core.errors import ComputeError
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


class TestGetNvidiaGpuNodeAffinity:
    def test_memory_requirement_is_preserved_from_offer_to_node_selection(self):
        nodes = [
            _gpu_node("NVIDIA-RTX-A2000", "6144"),
            _gpu_node("NVIDIA-RTX-A2000", "12288"),
        ]
        offers = [get_instance_offer_from_node(node, "ctx") for node in nodes]
        assert [offer.instance.resources.gpus[0].memory_mib for offer in offers] == [6144, 12288]
        assert all(len(offer.instance.resources.gpus) == 2 for offer in offers)

        affinity = _get_nvidia_gpu_node_affinity(ResourcesSpec(gpu="A2000:12GB").gpu, nodes)
        terms = affinity.required_during_scheduling_ignored_during_execution.node_selector_terms
        assert len(terms) == 1
        assert {rule.key: rule.values for rule in terms[0].match_expressions} == {
            "nvidia.com/gpu.product": ["NVIDIA-RTX-A2000"],
            "nvidia.com/gpu.memory": ["12288"],
        }

    def test_product_and_memory_pairs_cannot_be_combined_across_nodes(self):
        nodes = [_gpu_node("A100-SXM4-40GB", "39538"), _gpu_node("A100-SXM4-80GB", "80896")]
        affinity = _get_nvidia_gpu_node_affinity(ResourcesSpec(gpu="A100").gpu, nodes)
        terms = affinity.required_during_scheduling_ignored_during_execution.node_selector_terms
        assert [{rule.key: rule.values for rule in term.match_expressions} for term in terms] == [
            {
                "nvidia.com/gpu.product": ["A100-SXM4-40GB"],
                "nvidia.com/gpu.memory": ["39538"],
            },
            {
                "nvidia.com/gpu.product": ["A100-SXM4-80GB"],
                "nvidia.com/gpu.memory": ["80896"],
            },
        ]

    def test_does_not_select_a_smaller_capacity(self):
        with pytest.raises(ComputeError, match="no matching GPU labels"):
            _get_nvidia_gpu_node_affinity(
                ResourcesSpec(gpu="A2000:12GB").gpu, [_gpu_node("NVIDIA-RTX-A2000", "6144")]
            )

    def test_missing_product_warns_when_a_node_has_gpu_resources(self, caplog):
        node = _gpu_node("", "6144")
        offer = get_instance_offer_from_node(node, "ctx")
        assert offer.instance.resources.gpus == []
        assert "GPU resource found, but failed to detect its model or memory" in caplog.text


def _gpu_node(product: str, memory_mib: str) -> V1Node:
    return V1Node(
        metadata=V1ObjectMeta(
            name="gpu-node",
            labels={"nvidia.com/gpu.product": product, "nvidia.com/gpu.memory": memory_mib},
        ),
        spec=V1NodeSpec(),
        status=V1NodeStatus(allocatable={"cpu": "8", "memory": "64Gi", "nvidia.com/gpu": "2"}),
    )


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

    full_offers = list(
        compute.get_offers(requirements, full_offers=True, unallocated_resources=False)
    )

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

    adjusted_offers = list(
        compute.get_offers(requirements, full_offers=False, unallocated_resources=False)
    )

    assert len(adjusted_offers) == 1
    adjusted_resources = adjusted_offers[0].instance.resources
    assert adjusted_resources.cpus == 2
    assert adjusted_resources.memory_mib == 8 * 1024
    assert len(adjusted_resources.gpus) == 1
    assert adjusted_resources.disk.size_mib == 100 * 1024
