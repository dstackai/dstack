import logging
import uuid
from collections.abc import Generator
from datetime import datetime, timezone
from typing import Optional
from unittest.mock import MagicMock, Mock, patch

import pytest
from kubernetes import client
from kubernetes.client import V1Node, V1NodeSpec, V1NodeStatus, V1ObjectMeta
from kubernetes.client.exceptions import ApiException

from dstack._internal.core.backends.kubernetes.compute import (
    JUMP_POD_EPHEMERAL_STORAGE_REQUEST,
    KubernetesCompute,
    _check_and_configure_jump_pod_service,
    _create_jump_pod_service_if_not_exists,
    _get_pod_spec_parameters_for_gpu,
    _KubernetesSkipOfferCache,
)
from dstack._internal.core.backends.kubernetes.models import KubeconfigConfig, KubernetesConfig
from dstack._internal.core.backends.kubernetes.resources import (
    KubernetesOfferBackendData,
    build_base_labels,
    get_instance_offers,
)
from dstack._internal.core.errors import ProvisioningError
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import (
    Disk,
    Gpu,
    InstanceAvailability,
    InstanceOfferWithAvailability,
    InstanceType,
    Resources,
    SSHConnectionParams,
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
    requirements = Requirements(
        resources=ResourcesSpec.model_validate({"cpu": "2", "memory": "8GB", "gpu": "1"})
    )

    assert compute.get_offers_modifiers(requirements, full_offers=True) == []
    assert compute.get_offers_modifiers(requirements, full_offers=False) != []


def test_get_offers_with_full_offers_keeps_full_node_resources():
    compute = _compute()
    compute.get_all_offers_with_availability = MagicMock(return_value=[_node_offer()])
    # Open-ended requirements so the full node satisfies them without an upper bound.
    requirements = Requirements(
        resources=ResourcesSpec.model_validate(
            {"cpu": "2..", "memory": "8GB..", "gpu": "1..", "disk": "100GB.."}
        )
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
        resources=ResourcesSpec.model_validate(
            {"cpu": "2..", "memory": "8GB..", "gpu": "1..", "disk": "100GB.."}
        )
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


NAMESPACE = "dstack"
JUMP_POD_NAME = "dstack-main-ssh-jump-pod"
JUMP_POD_SERVICE_NAME = "dstack-main-ssh-jump-pod-service"
JUMP_POD_LABELS = build_base_labels(
    component="ssh-proxy",
    unique_name=JUMP_POD_NAME,
    project="main",
)
JUMP_POD_SELECTOR = {"app.kubernetes.io/instance": JUMP_POD_NAME}
# Both the labels and the service selector before https://github.com/dstackai/dstack/pull/3891
PRE_3891_JUMP_POD_LABELS = {"app.kubernetes.io/name": JUMP_POD_NAME}
GPU_NODE_TAINT = client.V1Taint(key="nvidia.com/gpu", value="present", effect="NoSchedule")


def _mock_read(method: Mock, obj: Optional[object]) -> None:
    if obj is None:
        method.side_effect = ApiException(status=404)
    else:
        method.return_value = obj


def _make_pod(
    *,
    name: str = JUMP_POD_NAME,
    labels: Optional[dict[str, str]] = None,
    phase: str = "Running",
    ready: bool = True,
    node_name: Optional[str] = "node-a",
    terminating: bool = False,
    unschedulable_message: Optional[str] = None,
) -> client.V1Pod:
    conditions = [client.V1PodCondition(type="Ready", status="True" if ready else "False")]
    if unschedulable_message is not None:
        conditions.append(
            client.V1PodCondition(
                type="PodScheduled",
                status="False",
                reason="Unschedulable",
                message=unschedulable_message,
            )
        )
    return client.V1Pod(
        metadata=client.V1ObjectMeta(
            name=name,
            labels=labels if labels is not None else JUMP_POD_LABELS,
            deletion_timestamp=(
                datetime(2026, 1, 1, tzinfo=timezone.utc) if terminating else None
            ),
        ),
        spec=client.V1PodSpec(containers=[], node_name=node_name),
        status=client.V1PodStatus(phase=phase, conditions=conditions),
    )


def _make_service(selector: dict[str, str], node_port: int) -> client.V1Service:
    return client.V1Service(
        metadata=client.V1ObjectMeta(name=JUMP_POD_SERVICE_NAME),
        spec=client.V1ServiceSpec(
            type="NodePort",
            selector=selector,
            ports=[client.V1ServicePort(port=22, target_port=22, node_port=node_port)],
        ),
    )


def _make_node(
    name: str,
    external_ip: Optional[str] = None,
    taints: Optional[list[client.V1Taint]] = None,
) -> client.V1Node:
    addresses: list[client.V1NodeAddress] = []
    if external_ip is not None:
        addresses.append(client.V1NodeAddress(type="ExternalIP", address=external_ip))
    return client.V1Node(
        metadata=client.V1ObjectMeta(name=name),
        spec=client.V1NodeSpec(taints=taints),
        status=client.V1NodeStatus(addresses=addresses),
    )


class TestCreateJumpPodServiceIfNotExists:
    def make_apis(
        self,
        *,
        namespace_exists: bool = True,
        pod: Optional[client.V1Pod] = None,
        replica_set: Optional[client.V1ReplicaSet] = None,
        service: Optional[client.V1Service] = None,
        nodes: Optional[list[client.V1Node]] = None,
    ) -> tuple[Mock, Mock]:
        api = Mock(spec=client.CoreV1Api)
        _mock_read(api.read_namespace, client.V1Namespace() if namespace_exists else None)
        _mock_read(api.read_namespaced_pod, pod)
        _mock_read(api.read_namespaced_service, service)
        if nodes is None:
            # An untainted node, so the jump pod needs no tolerations.
            nodes = [_make_node("node-a")]
        api.list_node.return_value = client.V1NodeList(items=nodes)
        apps_api = Mock(spec=client.AppsV1Api)
        _mock_read(apps_api.read_namespaced_replica_set, replica_set)
        return api, apps_api

    def call(
        self,
        api: Mock,
        apps_api: Mock,
        jump_pod_port: Optional[int] = None,
        cpu: str = "500m",
        memory: str = "1Gi",
        node_selector: Optional[list[str]] = None,
        tolerations: Optional[list[str]] = None,
    ) -> None:
        _create_jump_pod_service_if_not_exists(
            api=api,
            apps_api=apps_api,
            namespace=NAMESPACE,
            project_name="main",
            jump_pod_name=JUMP_POD_NAME,
            jump_pod_service_name=JUMP_POD_SERVICE_NAME,
            jump_pod_port=jump_pod_port,
            authorized_keys=["ssh-ed25519 AAAA project"],
            cpu_request_limit=cpu,
            memory_request_limit=memory,
            node_selector=node_selector,
            tolerations=tolerations,
        )

    def get_pod_spec(self, apps_api: Mock) -> client.V1PodSpec:
        apps_api.create_namespaced_replica_set.assert_called_once()
        replica_set = apps_api.create_namespaced_replica_set.call_args.kwargs["body"]
        return replica_set.spec.template.spec

    def assert_replica_set_created(
        self, apps_api: Mock, *, cpu: str = "500m", memory: str = "1Gi"
    ) -> None:
        apps_api.create_namespaced_replica_set.assert_called_once()
        replica_set = apps_api.create_namespaced_replica_set.call_args.kwargs["body"]
        assert replica_set.metadata.name == JUMP_POD_NAME
        assert replica_set.spec.replicas == 1
        assert replica_set.spec.selector.match_labels == JUMP_POD_SELECTOR
        assert replica_set.spec.template.metadata.labels == JUMP_POD_LABELS
        resources = replica_set.spec.template.spec.containers[0].resources
        # Equal CPU and memory requests and limits for the Guaranteed QoS class, and
        # an ephemeral-storage request without a limit
        assert resources.limits == {"cpu": cpu, "memory": memory}
        assert resources.requests == {
            "cpu": cpu,
            "memory": memory,
            "ephemeral-storage": JUMP_POD_EPHEMERAL_STORAGE_REQUEST,
        }

    def assert_service_created(
        self, api: Mock, *, selector: dict[str, str], node_port: Optional[int]
    ) -> None:
        api.create_namespaced_service.assert_called_once()
        service = api.create_namespaced_service.call_args.kwargs["body"]
        assert service.metadata.name == JUMP_POD_SERVICE_NAME
        assert service.spec.selector == selector
        assert service.spec.ports[0].node_port == node_port

    def test_creates_namespace_replica_set_and_service(self):
        api, apps_api = self.make_apis(namespace_exists=False)

        self.call(api, apps_api, jump_pod_port=30022)

        api.create_namespace.assert_called_once()
        api.read_namespaced_pod.assert_not_called()
        self.assert_replica_set_created(apps_api)
        self.assert_service_created(api, selector=JUMP_POD_SELECTOR, node_port=30022)

    def test_creates_replica_set_and_service_if_not_found(self):
        api, apps_api = self.make_apis()

        self.call(api, apps_api)

        api.create_namespace.assert_not_called()
        self.assert_replica_set_created(apps_api)
        self.assert_service_created(api, selector=JUMP_POD_SELECTOR, node_port=None)

    def test_sets_jump_pod_resources(self):
        api, apps_api = self.make_apis()

        self.call(api, apps_api, cpu="1", memory="2Gi")

        self.assert_replica_set_created(apps_api, cpu="1", memory="2Gi")

    def test_autodetects_tolerations_if_all_nodes_are_tainted(self):
        api, apps_api = self.make_apis(nodes=[_make_node("node-a", taints=[GPU_NODE_TAINT])])

        self.call(api, apps_api)

        pod_spec = self.get_pod_spec(apps_api)
        assert pod_spec.affinity is None
        assert pod_spec.tolerations == [
            client.V1Toleration(key="nvidia.com/gpu", operator="Exists", effect="NoSchedule")
        ]

    def test_sets_node_affinity_without_autodetected_tolerations(self):
        api, apps_api = self.make_apis(nodes=[_make_node("node-a", taints=[GPU_NODE_TAINT])])

        self.call(api, apps_api, node_selector=["example.com/jump-host", "example.com/pool=cpu"])

        pod_spec = self.get_pod_spec(apps_api)
        assert pod_spec.affinity == client.V1Affinity(
            node_affinity=client.V1NodeAffinity(
                required_during_scheduling_ignored_during_execution=client.V1NodeSelector(
                    # A single term, so that all requirements must match
                    node_selector_terms=[
                        client.V1NodeSelectorTerm(
                            match_expressions=[
                                client.V1NodeSelectorRequirement(
                                    key="example.com/jump-host", operator="Exists"
                                ),
                                client.V1NodeSelectorRequirement(
                                    key="example.com/pool", operator="In", values=["cpu"]
                                ),
                            ]
                        )
                    ]
                )
            )
        )
        assert pod_spec.tolerations == []
        api.list_node.assert_not_called()

    def test_empty_node_selector_disables_autodetected_tolerations(self):
        api, apps_api = self.make_apis(nodes=[_make_node("node-a", taints=[GPU_NODE_TAINT])])

        self.call(api, apps_api, node_selector=[])

        pod_spec = self.get_pod_spec(apps_api)
        # An empty node selector term would match no nodes
        assert pod_spec.affinity is None
        assert pod_spec.tolerations == []
        api.list_node.assert_not_called()

    @pytest.mark.parametrize("node_selector", [None, ["example.com/pool=cpu"]])
    @pytest.mark.parametrize(
        ["tolerations", "expected"],
        [
            pytest.param(
                ["example.com/pool=cpu:NoSchedule"],
                [
                    client.V1Toleration(
                        key="example.com/pool", operator="Equal", value="cpu", effect="NoSchedule"
                    )
                ],
                id="set",
            ),
            pytest.param([], [], id="empty"),
        ],
    )
    def test_sets_tolerations_without_autodetection(
        self,
        node_selector: Optional[list[str]],
        tolerations: list[str],
        expected: list[client.V1Toleration],
    ):
        api, apps_api = self.make_apis(nodes=[_make_node("node-a", taints=[GPU_NODE_TAINT])])

        self.call(api, apps_api, node_selector=node_selector, tolerations=tolerations)

        assert self.get_pod_spec(apps_api).tolerations == expected
        api.list_node.assert_not_called()

    def test_does_nothing_if_replica_set_and_service_exist(self):
        api, apps_api = self.make_apis(
            replica_set=client.V1ReplicaSet(
                spec=client.V1ReplicaSetSpec(
                    selector=client.V1LabelSelector(match_labels=JUMP_POD_SELECTOR),
                ),
            ),
            service=_make_service(JUMP_POD_SELECTOR, node_port=30022),
        )

        self.call(api, apps_api)

        apps_api.create_namespaced_replica_set.assert_not_called()
        api.delete_namespaced_service.assert_not_called()
        api.create_namespaced_service.assert_not_called()

    def test_creates_replica_set_to_adopt_running_legacy_pod(self):
        api, apps_api = self.make_apis(
            pod=_make_pod(),
            service=_make_service(JUMP_POD_SELECTOR, node_port=30022),
        )

        self.call(api, apps_api)

        api.delete_namespaced_pod.assert_not_called()
        self.assert_replica_set_created(apps_api)
        api.create_namespaced_service.assert_not_called()

    def test_deletes_finished_legacy_pod(self):
        api, apps_api = self.make_apis(
            pod=_make_pod(phase="Failed", ready=False),
            service=_make_service(JUMP_POD_SELECTOR, node_port=30022),
        )

        self.call(api, apps_api)

        api.delete_namespaced_pod.assert_called_once_with(namespace=NAMESPACE, name=JUMP_POD_NAME)
        self.assert_replica_set_created(apps_api)
        api.create_namespaced_service.assert_not_called()

    def test_keeps_running_pre_3891_pod_and_its_service(self):
        api, apps_api = self.make_apis(
            pod=_make_pod(labels=PRE_3891_JUMP_POD_LABELS),
            service=_make_service(PRE_3891_JUMP_POD_LABELS, node_port=30022),
        )

        self.call(api, apps_api)

        api.delete_namespaced_pod.assert_not_called()
        apps_api.create_namespaced_replica_set.assert_not_called()
        api.delete_namespaced_service.assert_not_called()
        api.create_namespaced_service.assert_not_called()

    def test_creates_service_with_old_selector_for_running_pre_3891_pod(self):
        api, apps_api = self.make_apis(pod=_make_pod(labels=PRE_3891_JUMP_POD_LABELS))

        self.call(api, apps_api, jump_pod_port=30022)

        apps_api.create_namespaced_replica_set.assert_not_called()
        self.assert_service_created(api, selector=PRE_3891_JUMP_POD_LABELS, node_port=30022)

    # The NodePort of the existing service wins even if proxy_jump.port is set
    @pytest.mark.parametrize("jump_pod_port", [None, 30022])
    def test_recreates_pre_3891_service_with_same_node_port(self, jump_pod_port: Optional[int]):
        api, apps_api = self.make_apis(
            pod=_make_pod(labels=PRE_3891_JUMP_POD_LABELS, phase="Failed", ready=False),
            service=_make_service(PRE_3891_JUMP_POD_LABELS, node_port=31234),
        )

        self.call(api, apps_api, jump_pod_port=jump_pod_port)

        api.delete_namespaced_pod.assert_called_once_with(namespace=NAMESPACE, name=JUMP_POD_NAME)
        self.assert_replica_set_created(apps_api)
        api.delete_namespaced_service.assert_called_once_with(
            namespace=NAMESPACE, name=JUMP_POD_SERVICE_NAME
        )
        self.assert_service_created(api, selector=JUMP_POD_SELECTOR, node_port=31234)
        # The other way round, the create would fail with an ignored 409 and leave no service
        method_names = [name for name, _, _ in api.method_calls]
        assert method_names.index("delete_namespaced_service") < method_names.index(
            "create_namespaced_service"
        )

    def test_ignores_conflicts_on_create(self):
        api, apps_api = self.make_apis(namespace_exists=False)
        api.create_namespace.side_effect = ApiException(status=409)
        apps_api.create_namespaced_replica_set.side_effect = ApiException(status=409)
        api.create_namespaced_service.side_effect = ApiException(status=409)

        self.call(api, apps_api)

        apps_api.create_namespaced_replica_set.assert_called_once()
        api.create_namespaced_service.assert_called_once()


class TestCheckAndConfigureJumpPodService:
    @pytest.fixture(autouse=True)
    def run_ssh_command_mock(self) -> Generator[Mock, None, None]:
        with patch(
            "dstack._internal.core.backends.kubernetes.compute._run_ssh_command",
            return_value=(0, b""),
        ) as run_ssh_command_mock:
            yield run_ssh_command_mock

    def make_api(
        self, *, pods: list[client.V1Pod], pre_3891_pod: Optional[client.V1Pod] = None
    ) -> Mock:
        api = Mock(spec=client.CoreV1Api)
        api.list_namespaced_pod.return_value = client.V1PodList(items=pods)
        _mock_read(api.read_namespaced_pod, pre_3891_pod)
        api.list_node.return_value = client.V1NodeList(
            items=[
                _make_node("node-a", external_ip="203.0.113.1"),
                _make_node("node-b", external_ip="203.0.113.2"),
            ]
        )
        api.read_namespaced_service.return_value = _make_service(
            JUMP_POD_SELECTOR, node_port=30022
        )
        return api

    def call(self, api: Mock) -> Optional[SSHConnectionParams]:
        return _check_and_configure_jump_pod_service(
            api=api,
            namespace=NAMESPACE,
            jump_pod_name=JUMP_POD_NAME,
            jump_pod_service_name=JUMP_POD_SERVICE_NAME,
            jump_pod_hostname=None,
            project_ssh_private_key="private-key",
            authorized_keys=[],
        )

    def test_returns_ssh_proxy_on_node_of_ready_pod(self):
        api = self.make_api(
            pods=[
                _make_pod(name="evicted", phase="Failed", ready=False, node_name="node-a"),
                _make_pod(name="ready", node_name="node-b"),
            ]
        )

        ssh_proxy = self.call(api)

        assert ssh_proxy == SSHConnectionParams(
            hostname="203.0.113.2", port=30022, username="root"
        )
        api.list_namespaced_pod.assert_called_once_with(
            namespace=NAMESPACE, label_selector=f"app.kubernetes.io/instance={JUMP_POD_NAME}"
        )
        api.read_namespaced_pod.assert_not_called()

    @pytest.mark.parametrize(
        "pod",
        [
            pytest.param(_make_pod(phase="Pending", ready=False, node_name=None), id="pending"),
            pytest.param(_make_pod(phase="Failed", ready=False), id="evicted"),
            pytest.param(_make_pod(terminating=True), id="terminating"),
        ],
    )
    def test_waits_if_no_pod_is_ready(
        self, caplog: pytest.LogCaptureFixture, run_ssh_command_mock: Mock, pod: client.V1Pod
    ):
        caplog.set_level(logging.WARNING)
        api = self.make_api(pods=[pod])

        assert self.call(api) is None
        api.read_namespaced_pod.assert_not_called()
        run_ssh_command_mock.assert_not_called()
        assert "cannot be scheduled" not in caplog.text

    def test_warns_if_pod_cannot_be_scheduled(
        self, caplog: pytest.LogCaptureFixture, run_ssh_command_mock: Mock
    ):
        caplog.set_level(logging.WARNING)
        api = self.make_api(
            pods=[
                _make_pod(
                    name="pending",
                    phase="Pending",
                    ready=False,
                    node_name=None,
                    unschedulable_message="0/3 nodes are available: 3 Insufficient memory.",
                ),
            ]
        )

        assert self.call(api) is None
        run_ssh_command_mock.assert_not_called()
        assert (
            "Jump pod pending cannot be scheduled: Unschedulable:"
            " 0/3 nodes are available: 3 Insufficient memory."
        ) in caplog.text

    def test_waits_if_no_pods(self, run_ssh_command_mock: Mock):
        # E.g., the ReplicaSet has not created a pod yet.
        api = self.make_api(pods=[])

        assert self.call(api) is None
        api.read_namespaced_pod.assert_called_once_with(namespace=NAMESPACE, name=JUMP_POD_NAME)
        run_ssh_command_mock.assert_not_called()

    def test_returns_ssh_proxy_if_pre_3891_pod_is_ready(self):
        api = self.make_api(
            pods=[],
            pre_3891_pod=_make_pod(labels=PRE_3891_JUMP_POD_LABELS, node_name="node-a"),
        )

        ssh_proxy = self.call(api)

        assert ssh_proxy == SSHConnectionParams(
            hostname="203.0.113.1", port=30022, username="root"
        )

    def test_raises_if_pre_3891_pod_is_finished(self, run_ssh_command_mock: Mock):
        api = self.make_api(
            pods=[],
            pre_3891_pod=_make_pod(labels=PRE_3891_JUMP_POD_LABELS, phase="Failed", ready=False),
        )

        with pytest.raises(ProvisioningError, match="unexpectedly finished"):
            self.call(api)
        run_ssh_command_mock.assert_not_called()


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
        resources=ResourcesSpec.model_validate(
            {"cpu": "2..", "memory": "8GB..", "disk": "100GB..", "gpu": gpu}
        )
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
        assert node_selector is not None
        [term] = node_selector.node_selector_terms
        assert term.match_expressions is not None
        [expression] = term.match_expressions
        assert expression.key == "nvidia.com/gpu.product"
        assert expression.values is not None
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
