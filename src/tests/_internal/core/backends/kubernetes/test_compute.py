import uuid
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest
from kubernetes.client import V1Node, V1NodeSpec, V1NodeStatus, V1ObjectMeta

from dstack._internal.core.backends.kubernetes.compute import (
    KubernetesCompute,
    _get_pod_spec_parameters_for_gpu,
    _KubernetesSkipOfferCache,
)
from dstack._internal.core.backends.kubernetes.models import KubeconfigConfig, KubernetesConfig
from dstack._internal.core.backends.kubernetes.resources import (
    KubernetesOfferBackendData,
    get_instance_offers,
)
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import (
    Disk,
    Gpu,
    InstanceAvailability,
    InstanceOfferWithAvailability,
    InstanceType,
    Resources,
)
from dstack._internal.core.models.resources import GPUSpec, ResourcesSpec
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


def _node(name: str, gpu_product: str, gpu_allocatable: dict[str, str]) -> V1Node:
    # Labels and resources as published by NVIDIA GPU Feature Discovery and the device plugin
    return V1Node(
        metadata=V1ObjectMeta(name=name, labels={"nvidia.com/gpu.product": gpu_product}),
        spec=V1NodeSpec(),
        status=V1NodeStatus(
            allocatable={
                "cpu": "200",
                "memory": "1800Gi",
                "ephemeral-storage": "1000Gi",
                **gpu_allocatable,
            }
        ),
    )


def _api(nodes: list[V1Node]) -> MagicMock:
    api = MagicMock()
    api.list_node.return_value.items = nodes
    api.list_pod_for_all_namespaces.return_value.items = []
    return api


# A `mixed` strategy MIG node: 4 GPUs with MIG disabled, 2 GPUs as 7 x 1g.10gb,
# 2 GPUs as 2 x 3g.40gb
_MIXED_NODE = _node(
    "mixed",
    "NVIDIA-A100-SXM4-80GB",
    {"nvidia.com/gpu": "4", "nvidia.com/mig-1g.10gb": "14", "nvidia.com/mig-3g.40gb": "4"},
)
_SINGLE_NODE = _node("single", "NVIDIA-A100-SXM4-80GB-MIG-1g.10gb", {"nvidia.com/gpu": "56"})


class TestGetOffersWithMig:
    @pytest.mark.parametrize(
        ["gpu", "full_offers", "expected"],
        [
            # Without a GPU memory cap, runs only get whole GPUs
            pytest.param("A100", False, [("A100", 80, 1)], id="name"),
            pytest.param("24GB..", False, [("A100", 80, 1)], id="memory-without-cap"),
            pytest.param("A100:10GB", False, [("A100", 10, 1)], id="slice"),
            pytest.param("A100:10GB:2", False, [("A100", 10, 2)], id="two-slices"),
            pytest.param(
                "10GB..40GB", False, [("A100", 10, 1), ("A100", 40, 1)], id="memory-range"
            ),
            # The mixed node's MIG offers would duplicate its main offer
            pytest.param("0", False, [(None, 0, 0)], id="no-gpu"),
            # Full offers show what the node has, including slices
            pytest.param(
                "A100",
                True,
                [("A100", 80, 4), ("A100", 10, 14), ("A100", 40, 4)],
                id="full-offers",
            ),
            pytest.param(
                "0..",
                True,
                [("A100", 80, 4), ("A100", 10, 14), ("A100", 40, 4)],
                id="full-offers-no-gpu",
            ),
        ],
    )
    def test_mixed_strategy_node(
        self, gpu: str, full_offers: bool, expected: list[tuple[Optional[str], int, int]]
    ):
        assert _get_offer_gpus(_MIXED_NODE, gpu, full_offers) == expected

    @pytest.mark.parametrize(
        ["gpu", "expected"],
        [
            pytest.param("A100", [], id="name"),
            pytest.param("A100:10GB", [("A100", 10, 1)], id="slice"),
            pytest.param("0", [(None, 0, 0)], id="no-gpu"),
        ],
    )
    def test_single_strategy_node(self, gpu: str, expected: list[tuple[Optional[str], int, int]]):
        assert _get_offer_gpus(_SINGLE_NODE, gpu, full_offers=False) == expected


def _get_offer_gpus(
    node: V1Node, gpu: str, full_offers: bool
) -> list[tuple[Optional[str], int, int]]:
    compute = _compute()
    compute.get_all_offers_with_availability = MagicMock(
        return_value=get_instance_offers(_api([node]), "ctx", unallocated_resources=False)
    )
    requirements = Requirements(
        resources=ResourcesSpec(cpu="2..", memory="8GB..", disk="100GB..", gpu=gpu)
    )
    offers = compute.get_offers(requirements, full_offers=full_offers, unallocated_resources=False)
    result: list[tuple[Optional[str], int, int]] = []
    for offer in offers:
        gpus = offer.instance.resources.gpus
        if gpus:
            result.append((gpus[0].name, gpus[0].memory_mib // 1024, len(gpus)))
        else:
            result.append((None, 0, 0))
    return result


class TestGetPodSpecParametersForGpu:
    _NODES = [
        _node("whole", "NVIDIA-A100-SXM4-80GB", {"nvidia.com/gpu": "8"}),
        _SINGLE_NODE,
        _MIXED_NODE,
        _node("mixed-h100", "NVIDIA-H100-80GB-HBM3", {"nvidia.com/mig-1g.10gb": "7"}),
    ]

    @pytest.mark.parametrize(
        ["gpu", "mig_resource", "expected_resource", "expected_products"],
        [
            pytest.param(
                "A100",
                None,
                "nvidia.com/gpu",
                # The mixed node's product label is the parent GPU's, same as the whole node's
                ["NVIDIA-A100-SXM4-80GB"],
                id="whole-gpu-excludes-single-strategy-slices",
            ),
            pytest.param(
                "A100:10GB",
                None,
                "nvidia.com/gpu",
                ["NVIDIA-A100-SXM4-80GB-MIG-1g.10gb"],
                id="single-strategy-slice",
            ),
            pytest.param(
                "A100:10GB",
                "nvidia.com/mig-1g.10gb",
                "nvidia.com/mig-1g.10gb",
                # Only nodes with the MIG resource and the requested GPU model
                ["NVIDIA-A100-SXM4-80GB"],
                id="mixed-strategy-slice",
            ),
        ],
    )
    def test_nvidia(
        self,
        gpu: str,
        mig_resource: Optional[str],
        expected_resource: str,
        expected_products: list[str],
    ):
        gpu_resource, node_affinity, node_taint = _get_pod_spec_parameters_for_gpu(
            _api(self._NODES), GPUSpec.model_validate(gpu), mig_resource
        )
        assert gpu_resource == expected_resource
        assert node_taint == "nvidia.com/gpu"
        node_selector = node_affinity.required_during_scheduling_ignored_during_execution
        expression = node_selector.node_selector_terms[0].match_expressions[0]
        assert expression.key == "nvidia.com/gpu.product"
        assert sorted(expression.values) == expected_products


class TestKubernetesSkipOfferCache:
    def test_mig_offers_are_skipped_separately_by_mig_resource(self):
        cache = _KubernetesSkipOfferCache(ttl=60)
        run = MagicMock(id=uuid.uuid4())
        job = MagicMock()
        whole_offer = _node_offer()
        other_whole_offer = _node_offer()
        mig_offer = _mig_offer("nvidia.com/mig-1g.10gb")
        other_mig_offer = _mig_offer("nvidia.com/mig-3g.40gb")

        cache.add(run, job, mig_offer)
        assert cache.check(run, job, mig_offer)
        assert not cache.check(run, job, other_mig_offer)
        assert not cache.check(run, job, whole_offer)

        # As before, a failed offer that isn't a mixed strategy MIG offer skips all such offers
        # in the region
        cache.add(run, job, whole_offer)
        assert cache.check(run, job, other_whole_offer)
        assert not cache.check(run, job, other_mig_offer)
        assert not cache.check(MagicMock(id=uuid.uuid4()), job, other_whole_offer)


def _mig_offer(mig_resource: str) -> InstanceOfferWithAvailability:
    offer = _node_offer()
    offer.backend_data = KubernetesOfferBackendData(mig=True, mig_resource=mig_resource).dump()
    return offer
