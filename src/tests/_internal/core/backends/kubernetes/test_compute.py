from collections.abc import Generator
from datetime import datetime, timezone
from typing import Optional
from unittest.mock import MagicMock, Mock, patch

import pytest
from kubernetes import client
from kubernetes.client.exceptions import ApiException

from dstack._internal.core.backends.kubernetes.compute import (
    KubernetesCompute,
    _check_and_configure_jump_pod_service,
    _create_jump_pod_service_if_not_exists,
)
from dstack._internal.core.backends.kubernetes.models import KubeconfigConfig, KubernetesConfig
from dstack._internal.core.backends.kubernetes.resources import build_base_labels
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
) -> client.V1Pod:
    return client.V1Pod(
        metadata=client.V1ObjectMeta(
            name=name,
            labels=labels if labels is not None else JUMP_POD_LABELS,
            deletion_timestamp=(
                datetime(2026, 1, 1, tzinfo=timezone.utc) if terminating else None
            ),
        ),
        spec=client.V1PodSpec(containers=[], node_name=node_name),
        status=client.V1PodStatus(
            phase=phase,
            conditions=[
                client.V1PodCondition(type="Ready", status="True" if ready else "False"),
            ],
        ),
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


def _make_node(name: str, external_ip: Optional[str] = None) -> client.V1Node:
    addresses: list[client.V1NodeAddress] = []
    if external_ip is not None:
        addresses.append(client.V1NodeAddress(type="ExternalIP", address=external_ip))
    return client.V1Node(
        metadata=client.V1ObjectMeta(name=name),
        spec=client.V1NodeSpec(),
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
    ) -> tuple[Mock, Mock]:
        api = Mock(spec=client.CoreV1Api)
        _mock_read(api.read_namespace, client.V1Namespace() if namespace_exists else None)
        _mock_read(api.read_namespaced_pod, pod)
        _mock_read(api.read_namespaced_service, service)
        # An untainted node, so the jump pod needs no tolerations.
        api.list_node.return_value = client.V1NodeList(items=[_make_node("node-a")])
        apps_api = Mock(spec=client.AppsV1Api)
        _mock_read(apps_api.read_namespaced_replica_set, replica_set)
        return api, apps_api

    def call(self, api: Mock, apps_api: Mock, jump_pod_port: Optional[int] = None) -> None:
        _create_jump_pod_service_if_not_exists(
            api=api,
            apps_api=apps_api,
            namespace=NAMESPACE,
            project_name="main",
            jump_pod_name=JUMP_POD_NAME,
            jump_pod_service_name=JUMP_POD_SERVICE_NAME,
            jump_pod_port=jump_pod_port,
            authorized_keys=["ssh-ed25519 AAAA project"],
        )

    def assert_replica_set_created(self, apps_api: Mock) -> None:
        apps_api.create_namespaced_replica_set.assert_called_once()
        replica_set = apps_api.create_namespaced_replica_set.call_args.kwargs["body"]
        assert replica_set.metadata.name == JUMP_POD_NAME
        assert replica_set.spec.replicas == 1
        assert replica_set.spec.selector.match_labels == JUMP_POD_SELECTOR
        assert replica_set.spec.template.metadata.labels == JUMP_POD_LABELS

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
    def test_waits_if_no_pod_is_ready(self, run_ssh_command_mock: Mock, pod: client.V1Pod):
        api = self.make_api(pods=[pod])

        assert self.call(api) is None
        api.read_namespaced_pod.assert_not_called()
        run_ssh_command_mock.assert_not_called()

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
