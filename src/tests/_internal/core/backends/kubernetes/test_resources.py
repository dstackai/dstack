import logging
from decimal import Decimal
from typing import Optional
from unittest.mock import MagicMock

import pytest
from gpuhunt import AcceleratorVendor
from kubernetes.client import (
    V1Container,
    V1Node,
    V1NodeSpec,
    V1NodeStatus,
    V1ObjectMeta,
    V1Pod,
    V1PodSpec,
    V1PodStatus,
    V1ResourceRequirements,
)

from dstack._internal.core.backends.kubernetes.resources import (
    KubernetesOfferBackendData,
    KubernetesResource,
    KubernetesResources,
    ResourceLimits,
    ResourceRequests,
    adjust_resources_by_resource_requests,
    get_amd_gpu_from_node_labels,
    get_gpu_resource_from_kubernetes_map,
    get_instance_offer_from_node,
    get_instance_offers,
    get_nvidia_gpu_from_node_labels,
    is_nvidia_mig_product,
    validate_label_key,
    validate_label_value,
)
from dstack._internal.core.models.instances import Disk, Gpu, Resources
from dstack._internal.core.models.resources import (
    CPUSpec,
    DiskSpec,
    GPUSpec,
    Memory,
    Range,
    ResourcesSpec,
)


class TestGetNvidiaGPUFromNodeLabels:
    def test_returns_none_if_no_labels(self):
        assert get_nvidia_gpu_from_node_labels({}) is None

    def test_returns_correct_memory_for_different_A100(self):
        assert get_nvidia_gpu_from_node_labels(
            {"nvidia.com/gpu.product": "A100-SXM4-40GB"}
        ) == Gpu(vendor=AcceleratorVendor.NVIDIA, name="A100", memory_mib=40 * 1024)

        assert get_nvidia_gpu_from_node_labels(
            {"nvidia.com/gpu.product": "A100-SXM4-80GB"}
        ) == Gpu(vendor=AcceleratorVendor.NVIDIA, name="A100", memory_mib=80 * 1024)

    @pytest.mark.parametrize(
        ["product", "expected_name", "expected_memory_gb"],
        [
            # The label from NVIDIA's "MIG Support in Kubernetes" docs
            pytest.param("A100-SXM4-40GB-MIG-1g.5gb", "A100", 5, id="a100-40gb"),
            # The label set by GPU Operator v26.7.2 on GKE
            pytest.param("NVIDIA-A100-SXM4-40GB-MIG-1g.5gb", "A100", 5, id="a100-40gb-gke"),
            pytest.param("NVIDIA-A100-SXM4-80GB-MIG-1g.10gb", "A100", 10, id="a100-80gb"),
            pytest.param("NVIDIA-H100-80GB-HBM3-MIG-3g.40gb", "H100", 40, id="h100"),
            # GPU Feature Discovery replaces `+` with `.` in labels: 1g.5gb+me -> 1g.5gb.me
            pytest.param("NVIDIA-A100-SXM4-40GB-MIG-1g.5gb.me", "A100", 5, id="me-suffix"),
            pytest.param("NVIDIA-A100-SXM4-80GB-MIG-1g.10gb-SHARED", "A100", 10, id="shared"),
        ],
    )
    def test_returns_mig_profile_memory_for_single_strategy_slice(
        self, product: str, expected_name: str, expected_memory_gb: int
    ):
        assert get_nvidia_gpu_from_node_labels({"nvidia.com/gpu.product": product}) == Gpu(
            vendor=AcceleratorVendor.NVIDIA,
            name=expected_name,
            memory_mib=expected_memory_gb * 1024,
        )

    def test_returns_none_for_invalid_single_strategy_layout(
        self, caplog: pytest.LogCaptureFixture
    ):
        caplog.set_level(logging.WARNING)
        labels = {"nvidia.com/gpu.product": "NVIDIA-A100-SXM4-80GB-MIG-INVALID"}
        assert get_nvidia_gpu_from_node_labels(labels) is None
        assert "Failed to detect memory of MIG profile INVALID" in caplog.text

    @pytest.mark.parametrize(
        ["mig_resource", "expected_memory_gb"],
        [
            pytest.param("nvidia.com/mig-1g.10gb", 10, id="1g"),
            pytest.param("nvidia.com/mig-3g.40gb", 40, id="3g"),
            # The device plugin replaces `+` with `.`: 1g.10gb+me -> mig-1g.10gb.me
            pytest.param("nvidia.com/mig-1g.10gb.me", 10, id="me-suffix"),
        ],
    )
    def test_returns_mig_resource_memory_for_mixed_strategy_slice(
        self, mig_resource: str, expected_memory_gb: int
    ):
        # With the mixed strategy, the product label is the parent GPU's
        labels = {"nvidia.com/gpu.product": "NVIDIA-A100-SXM4-80GB"}
        assert get_nvidia_gpu_from_node_labels(labels, mig_resource) == Gpu(
            vendor=AcceleratorVendor.NVIDIA, name="A100", memory_mib=expected_memory_gb * 1024
        )


class TestIsNvidiaMigProduct:
    def test_true_for_single_strategy_slice(self):
        labels = {"nvidia.com/gpu.product": "NVIDIA-A100-SXM4-80GB-MIG-1g.10gb"}
        assert is_nvidia_mig_product(labels)

    @pytest.mark.parametrize(
        "labels",
        [
            pytest.param({}, id="no-labels"),
            pytest.param({"nvidia.com/gpu.product": "NVIDIA-A100-SXM4-80GB"}, id="whole-gpu"),
        ],
    )
    def test_false_for_whole_gpu(self, labels: dict[str, str]):
        assert not is_nvidia_mig_product(labels)


class TestGetAMDGPUFromNodeLabels:
    def test_returns_no_gpus_if_no_labels(self):
        assert get_amd_gpu_from_node_labels({}) is None

    def test_returns_known_gpu(self):
        assert get_amd_gpu_from_node_labels({"beta.amd.com/gpu.device-id.74b5": "4"}) == Gpu(
            vendor=AcceleratorVendor.AMD, name="MI300X", memory_mib=192 * 1024
        )

    def test_returns_known_gpu_if_multiple_device_ids_match_the_same_gpu(self):
        # 4x AMD Instinct MI300X VF + 4x AMD Instinct MI300X
        labels = {"beta.amd.com/gpu.device-id.74b5": "4", "beta.amd.com/gpu.device-id.74a1": "4"}
        assert get_amd_gpu_from_node_labels(labels) == Gpu(
            vendor=AcceleratorVendor.AMD, name="MI300X", memory_mib=192 * 1024
        )

    def test_returns_none_if_device_id_is_unknown(self, caplog: pytest.LogCaptureFixture):
        caplog.set_level(logging.WARNING)
        assert get_amd_gpu_from_node_labels({"beta.amd.com/gpu.device-id.ffff": "4"}) is None
        assert "Unknown AMD GPU device id: FFFF" in caplog.text

    def test_returns_none_if_multiple_gpu_models(self, caplog: pytest.LogCaptureFixture):
        caplog.set_level(logging.WARNING)
        # 4x AMD Instinct MI300X VF + 4x AMD Instinct MI325X
        labels = {"beta.amd.com/gpu.device-id.74b5": "4", "beta.amd.com/gpu.device-id.74a5": "4"}
        assert get_amd_gpu_from_node_labels(labels) is None
        assert "Multiple AMD GPU models detected" in caplog.text


class TestResourceRequests:
    def test_from_resources_spec_uses_lower_bounds_and_defaults_unset_to_zero(self):
        spec = ResourcesSpec(
            cpu=CPUSpec(count=Range[int](min=None, max=64)),
            memory=Range[Memory](min=Memory.parse("1024GB"), max=Memory.parse("1024GB")),
            disk=DiskSpec(size=Range[Memory](min=Memory.parse("100GB"), max=None)),
            gpu=GPUSpec(count=Range[int](min=4, max=8)),
        )
        assert ResourceRequests.from_resources_spec(spec) == ResourceRequests(
            cpu=0, memory_mib=1024 * 1024, disk_mib=100 * 1024, gpu=4
        )

    def test_to_kubernetes_map(self):
        requests = ResourceRequests(cpu=0, memory_mib=1024 * 1024, disk_mib=100 * 1024, gpu=4)
        assert requests.to_kubernetes_map(KubernetesResource.NVIDIA_GPU) == {
            "cpu": "0",
            "memory": "1048576Mi",
            "ephemeral-storage": "102400Mi",
            "nvidia.com/gpu": "4",
        }

    def test_kubernetes_map_round_trip(self):
        requests = ResourceRequests(cpu=8, memory_mib=16384, disk_mib=51200, gpu=2)
        map_ = requests.to_kubernetes_map(KubernetesResource.AMD_GPU)
        assert ResourceRequests.from_kubernetes_map(map_) == requests

    def test_kubernetes_map_round_trip_with_mig_resource(self):
        requests = ResourceRequests(cpu=8, memory_mib=16384, disk_mib=51200, gpu=2)
        map_ = requests.to_kubernetes_map("nvidia.com/mig-1g.10gb")
        assert map_["nvidia.com/mig-1g.10gb"] == "2"
        assert ResourceRequests.from_kubernetes_map(map_) == requests


class TestGetGpuResourceFromKubernetesMap:
    @pytest.mark.parametrize(
        ["map_", "expected"],
        [
            pytest.param({"cpu": "1"}, None, id="no-gpu"),
            pytest.param({"cpu": "1", "nvidia.com/gpu": "1"}, "nvidia.com/gpu", id="nvidia"),
            pytest.param({"cpu": "1", "amd.com/gpu": "1"}, "amd.com/gpu", id="amd"),
            pytest.param(
                {"cpu": "1", "nvidia.com/mig-1g.10gb": "1"}, "nvidia.com/mig-1g.10gb", id="mig"
            ),
        ],
    )
    def test_returns_gpu_resource(self, map_: dict[str, str], expected: Optional[str]):
        assert get_gpu_resource_from_kubernetes_map(map_) == expected


class TestKubernetesResources:
    def test_from_kubernetes_map_includes_mig_resources(self):
        resources = KubernetesResources.from_kubernetes_map(
            {"cpu": "8", "nvidia.com/gpu": "4", "nvidia.com/mig-1g.10gb": "14"}
        )
        assert resources.nvidia_gpu == 4
        assert resources["nvidia.com/mig-1g.10gb"] == 14
        assert resources["nvidia.com/mig-3g.40gb"] == 0

    def test_subtracts_mig_resources(self):
        allocatable = KubernetesResources.from_kubernetes_map(
            {"cpu": "8", "nvidia.com/mig-1g.10gb": "14", "nvidia.com/mig-3g.40gb": "4"}
        )
        allocated = KubernetesResources.from_kubernetes_map(
            {"cpu": "2", "nvidia.com/mig-1g.10gb": "5"}
        )
        assert allocatable - allocated == KubernetesResources(
            cpu=Decimal(6),
            nvidia_mig={
                "nvidia.com/mig-1g.10gb": Decimal(9),
                "nvidia.com/mig-3g.40gb": Decimal(4),
            },
        )


class TestResourceLimits:
    def test_from_resources_spec_uses_upper_bounds_and_leaves_unset_as_none(self):
        spec = ResourcesSpec(
            cpu=CPUSpec(count=Range[int](min=None, max=64)),
            memory=Range[Memory](min=Memory.parse("1024GB"), max=Memory.parse("1024GB")),
            disk=DiskSpec(size=Range[Memory](min=Memory.parse("100GB"), max=None)),
            gpu=GPUSpec(count=Range[int](min=4, max=8)),
        )
        # GPU limit must equal the request (min), since GPUs cannot be overcommitted.
        assert ResourceLimits.from_resources_spec(spec) == ResourceLimits(
            cpu=64, memory_mib=1024 * 1024, disk_mib=None, gpu=4
        )

    def test_to_kubernetes_map_omits_unset_resources(self):
        limits = ResourceLimits(cpu=64, memory_mib=1024 * 1024, disk_mib=None, gpu=4)
        assert limits.to_kubernetes_map(KubernetesResource.NVIDIA_GPU) == {
            "cpu": "64",
            "memory": "1048576Mi",
            "nvidia.com/gpu": "4",
        }


def _node_resources() -> Resources:
    return Resources(
        cpus=64,
        memory_mib=256 * 1024,
        gpus=[Gpu(name="H100", memory_mib=80 * 1024)] * 8,
        disk=Disk(size_mib=1000 * 1024),
        spot=False,
    )


class TestAdjustResourcesByResourceRequests:
    def test_clamps_each_resource_to_the_smaller_of_node_and_request(self):
        resources = _node_resources()
        adjust_resources_by_resource_requests(
            resources,
            ResourceRequests(cpu=8, memory_mib=16 * 1024, disk_mib=100 * 1024, gpu=2),
        )
        assert resources.cpus == 8
        assert resources.memory_mib == 16 * 1024
        assert resources.disk == Disk(size_mib=100 * 1024)
        assert len(resources.gpus) == 2

    def test_does_not_exceed_node_resources(self):
        resources = _node_resources()
        adjust_resources_by_resource_requests(
            resources,
            ResourceRequests(cpu=128, memory_mib=512 * 1024, disk_mib=4000 * 1024, gpu=16),
        )
        assert resources.cpus == 64
        assert resources.memory_mib == 256 * 1024
        assert resources.disk == Disk(size_mib=1000 * 1024)
        assert len(resources.gpus) == 8

    def test_force_sets_resources_to_the_request(self):
        resources = _node_resources()
        adjust_resources_by_resource_requests(
            resources,
            ResourceRequests(cpu=8, memory_mib=16 * 1024, disk_mib=100 * 1024, gpu=2),
            force=True,
        )
        assert resources.cpus == 8
        assert resources.memory_mib == 16 * 1024
        assert resources.disk == Disk(size_mib=100 * 1024)
        assert len(resources.gpus) == 2


class TestLabelValidation:
    @pytest.mark.parametrize(
        "key",
        [
            pytest.param("env", id="private"),
            pytest.param("k8s.example.com/Valid.Label_Name-1", id="prefixed"),
        ],
    )
    def test_valid_key(self, key: str):
        validate_label_key(key)

    @pytest.mark.parametrize(
        ["key", "expected_error"],
        [
            pytest.param("app.kubernetes.io//name", "Too many segments", id="too-many-segments"),
            pytest.param("/name", "Empty prefix", id="empty-prefix"),
            pytest.param("a" * 254 + "/name", "Prefix too long", id="too-long-prefix"),
            pytest.param("invalid prefix/name", "Invalid prefix", id="space-in-prefix"),
            pytest.param("my_app/name", "Invalid prefix", id="underscore-in-prefix"),
            pytest.param("-invalid/name", "Invalid prefix", id="leading-dash-in-prefix"),
            pytest.param("invalid-/name", "Invalid prefix", id="trailing-dash-in-prefix"),
            pytest.param("Invalid/name", "Invalid prefix", id="uppercase-in-prefix"),
            pytest.param("", "Empty name", id="empty-name-no-prefix"),
            pytest.param("prefix/", "Empty name", id="empty-name-with-prefix"),
            pytest.param("a" * 64, "Name too long", id="too-long-name-no-prefix"),
            pytest.param("prefix/" + "a" * 64, "Name too long", id="too-long-name-with-prefix"),
            pytest.param("-name", "Invalid name", id="leading-dash-in-name"),
            pytest.param("name-", "Invalid name", id="trailing-dash-in-name"),
        ],
    )
    def test_invalid_key(self, key: str, expected_error: str):
        with pytest.raises(ValueError, match=expected_error):
            validate_label_key(key)

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param("", id="empty"),
            pytest.param("Valid.Label_Value-1", id="non-empty"),
        ],
    )
    def test_valid_value(self, value: str):
        validate_label_value(value)

    @pytest.mark.parametrize(
        ["value", "expected_error"],
        [
            pytest.param("a" * 64, "Value too long", id="too-long"),
            pytest.param("invalid value", "Invalid value", id="space"),
            pytest.param("-invalid", "Invalid value", id="leading-dash"),
            pytest.param("invalid-", "Invalid value", id="trailing-dash"),
        ],
    )
    def test_invalid_value(self, value: str, expected_error: str):
        with pytest.raises(ValueError, match=expected_error):
            validate_label_value(value)


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


def _pod(node_name: str, requests: dict[str, str]) -> V1Pod:
    return V1Pod(
        spec=V1PodSpec(
            node_name=node_name,
            containers=[
                V1Container(name="c", resources=V1ResourceRequirements(requests=requests))
            ],
        ),
        status=V1PodStatus(phase="Running"),
    )


def _api(nodes: list[V1Node], pods: Optional[list[V1Pod]] = None) -> MagicMock:
    api = MagicMock()
    api.list_node.return_value.items = nodes
    api.list_pod_for_all_namespaces.return_value.items = pods or []
    return api


# 4 GPUs with MIG disabled, 2 GPUs as 7 x 1g.10gb, 2 GPUs as 2 x 3g.40gb
_MIXED_NODE_GPU_ALLOCATABLE = {
    "nvidia.com/gpu": "4",
    "nvidia.com/mig-1g.10gb": "14",
    "nvidia.com/mig-3g.40gb": "4",
}


def _offer_gpus(offer) -> tuple[Optional[str], int, int, KubernetesOfferBackendData]:
    gpus = offer.instance.resources.gpus
    return (
        gpus[0].name if gpus else None,
        gpus[0].memory_mib // 1024 if gpus else 0,
        len(gpus),
        KubernetesOfferBackendData.load(offer.backend_data),
    )


class TestGetInstanceOffers:
    def test_node_without_mig_has_one_offer_with_empty_backend_data(self):
        api = _api([_node("node", "NVIDIA-A100-SXM4-80GB", {"nvidia.com/gpu": "8"})])
        offers = get_instance_offers(api, "ctx", unallocated_resources=False)
        assert len(offers) == 1
        assert offers[0].backend_data == {}
        assert _offer_gpus(offers[0])[:3] == ("A100", 80, 8)

    def test_single_strategy_node_offers_slices(self):
        api = _api([_node("node", "NVIDIA-A100-SXM4-80GB-MIG-1g.10gb", {"nvidia.com/gpu": "56"})])
        offers = get_instance_offers(api, "ctx", unallocated_resources=False)
        assert [_offer_gpus(o) for o in offers] == [
            ("A100", 10, 56, KubernetesOfferBackendData(mig=True)),
        ]

    def test_mixed_strategy_node_has_offer_per_mig_resource(self):
        api = _api([_node("node", "NVIDIA-A100-SXM4-80GB", _MIXED_NODE_GPU_ALLOCATABLE)])
        offers = get_instance_offers(api, "ctx", unallocated_resources=False)
        assert [_offer_gpus(o) for o in offers] == [
            ("A100", 80, 4, KubernetesOfferBackendData()),
            (
                "A100",
                10,
                14,
                KubernetesOfferBackendData(mig=True, mig_resource="nvidia.com/mig-1g.10gb"),
            ),
            (
                "A100",
                40,
                4,
                KubernetesOfferBackendData(mig=True, mig_resource="nvidia.com/mig-3g.40gb"),
            ),
        ]
        # The offers share the node's CPU, memory, and disk
        assert {o.instance.name for o in offers} == {"node"}
        assert {o.instance.resources.cpus for o in offers} == {200}

    def test_mixed_strategy_node_skips_mig_resources_with_no_slices(self):
        # After a MIG layout change, the device plugin keeps the old resources at 0
        # (as seen on GKE with GPU Operator v26.7.2)
        gpu_allocatable = {
            "nvidia.com/gpu": "0",
            "nvidia.com/mig-1g.5gb": "0",
            "nvidia.com/mig-3g.20gb": "1",
            "nvidia.com/mig-4g.20gb": "1",
        }
        api = _api([_node("node", "NVIDIA-A100-SXM4-40GB", gpu_allocatable)])
        offers = get_instance_offers(api, "ctx", unallocated_resources=False)
        assert [_offer_gpus(o) for o in offers] == [
            (None, 0, 0, KubernetesOfferBackendData()),
            (
                "A100",
                20,
                1,
                KubernetesOfferBackendData(mig=True, mig_resource="nvidia.com/mig-3g.20gb"),
            ),
            (
                "A100",
                20,
                1,
                KubernetesOfferBackendData(mig=True, mig_resource="nvidia.com/mig-4g.20gb"),
            ),
        ]

    def test_unallocated_resources_subtract_mig_slices(self):
        api = _api(
            [_node("node", "NVIDIA-A100-SXM4-80GB", _MIXED_NODE_GPU_ALLOCATABLE)],
            pods=[
                _pod("node", {"cpu": "50", "nvidia.com/gpu": "2"}),
                _pod("node", {"nvidia.com/mig-1g.10gb": "5"}),
                _pod("node", {"nvidia.com/mig-3g.40gb": "4"}),
            ],
        )
        offers = get_instance_offers(api, "ctx", unallocated_resources=True)
        # No 3g.40gb offer: all of its slices are in use
        assert [_offer_gpus(o)[:3] for o in offers] == [("A100", 80, 2), ("A100", 10, 9)]
        assert {o.instance.resources.cpus for o in offers} == {150}


class TestGetInstanceOfferFromNode:
    @pytest.mark.parametrize(
        ["gpu_resource", "expected_memory_gb", "expected_count"],
        [
            pytest.param(None, 80, 4, id="no-gpu"),
            pytest.param("nvidia.com/gpu", 80, 4, id="whole-gpu"),
            pytest.param("nvidia.com/mig-3g.40gb", 40, 4, id="mig"),
        ],
    )
    def test_returns_offer_for_gpu_resource(
        self, gpu_resource: Optional[str], expected_memory_gb: int, expected_count: int
    ):
        node = _node("node", "NVIDIA-A100-SXM4-80GB", _MIXED_NODE_GPU_ALLOCATABLE)
        offer = get_instance_offer_from_node(node, "ctx", gpu_resource)
        assert offer is not None
        assert _offer_gpus(offer)[1:3] == (expected_memory_gb, expected_count)
