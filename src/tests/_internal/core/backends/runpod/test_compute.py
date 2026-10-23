from datetime import datetime, timezone
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest

from dstack._internal.core.backends.base.compute import parse_provider_ref_from_name
from dstack._internal.core.backends.runpod.api_client import RunpodV2ClientError
from dstack._internal.core.backends.runpod.compute import RunpodCompute
from dstack._internal.core.backends.runpod.models import RunpodAPIKeyCreds, RunpodConfig
from dstack._internal.core.errors import ComputeError
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.backends.orphans import ListedResourceGroup, OwnerType
from dstack._internal.core.models.instances import InstanceOfferWithAvailability
from dstack._internal.core.models.resources import ResourcesSpec
from dstack._internal.core.models.runs import JobProvisioningData, Requirements
from dstack._internal.server.testing.common import (
    get_instance_offer_with_availability,
    get_job_provisioning_data,
)

# build_authorized_keys() rejects the project key unless it actually parses
PROJECT_SSH_PUBLIC_KEY = (
    "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAINOmx0T+hBRaJ6jCi21ZYe2NW3EZS8e0Mdwl+yZJt+kD project"
)


def _compute() -> RunpodCompute:
    compute = RunpodCompute(RunpodConfig(creds=RunpodAPIKeyCreds(api_key="test")))
    compute.api_client = MagicMock()
    return compute


def _gpu_offer(
    *, gpu_count: int = 2, cpu_count: int = 15, memory_gib: float = 251
) -> InstanceOfferWithAvailability:
    return get_instance_offer_with_availability(
        backend=BackendType.RUNPOD,
        region="EU-RO-1",
        gpu_count=gpu_count,
        gpu_name="H100",
        cpu_count=cpu_count,
        memory_gib=memory_gib,
        instance_type="NVIDIA H100 80GB HBM3",
    )


def _cluster_offer(pod_counts: list[int]) -> InstanceOfferWithAvailability:
    offer = _gpu_offer(gpu_count=8, cpu_count=128, memory_gib=1024)
    offer.backend_data = {"pod_counts": pod_counts}
    return offer


def _job() -> MagicMock:
    job = MagicMock()
    job.job_spec.job_name = "test-job-0"
    job.job_spec.image_name = "dstackai/base:latest"
    job.job_spec.registry_auth = None
    return job


def _run() -> MagicMock:
    run = MagicMock()
    run.project_name = "main"
    run.user = "test-user"
    return run


def _run_job(
    compute: RunpodCompute,
    offer: InstanceOfferWithAvailability,
    job: Optional[MagicMock] = None,
) -> JobProvisioningData:
    with patch(
        "dstack._internal.core.backends.runpod.compute.get_docker_commands",
        return_value=["echo hi"],
    ):
        return compute.run_job(
            run=_run(),
            job=job if job is not None else _job(),
            instance_offer=offer,
            project_ssh_public_key=PROJECT_SSH_PUBLIC_KEY,
            project_ssh_private_key="private-key",
            volumes=[],
            placement_group=None,
            requirements=Requirements(resources=ResourcesSpec()),
            extra_authorized_keys=[],
        )


def _run_jobs(compute: RunpodCompute, offer: InstanceOfferWithAvailability, job_count: int):
    job_configurations = []
    for _ in range(job_count):
        job_configuration = MagicMock()
        job_configuration.job = _job()
        job_configuration.volumes = []
        job_configurations.append(job_configuration)
    with patch(
        "dstack._internal.core.backends.runpod.compute.get_docker_commands",
        return_value=["echo hi"],
    ):
        return compute.run_jobs(
            run=_run(),
            job_configurations=job_configurations,
            instance_offer=offer,
            project_ssh_public_key=PROJECT_SSH_PUBLIC_KEY,
            project_ssh_private_key="private-key",
            placement_group=None,
            requirements=Requirements(resources=ResourcesSpec(), multinode=True),
            extra_authorized_keys=[],
        )


def _pod(
    pod_id: str = "pod-1",
    *,
    ports: Optional[list[dict]] = None,
    cluster_ip: Optional[str] = None,
    is_cluster_pod: bool = False,
) -> dict:
    pod: dict = {
        "id": pod_id,
        "status": "RUNNING",
        "runtime": None if ports is None else {"ports": ports},
        "mounts": {},
    }
    if is_cluster_pod or cluster_ip is not None:
        pod["cluster"] = {"id": "cluster-1", "rank": 0}
        if cluster_ip is not None:
            pod["cluster"]["ip"] = cluster_ip
    return pod


SSH_PORTS = [
    {"ip": "100.65.0.1", "private": 8080, "public": None, "type": "http"},
    {"ip": "203.0.113.10", "private": 10022, "public": 40022, "type": "tcp"},
]


class TestRunpodComputeRunJob:
    def test_requests_per_gpu_minimums_rounded_down(self):
        compute = _compute()
        compute.api_client.create_pod.return_value = {"id": "pod-1"}

        jpd = _run_job(compute, _gpu_offer(gpu_count=2, cpu_count=15, memory_gib=251))

        assert jpd.instance_id == "pod-1"
        kwargs = compute.api_client.create_pod.call_args.kwargs
        assert kwargs["cloud"] == "SECURE"
        assert kwargs["data_center_ids"] == ["EU-RO-1"]
        assert kwargs["gpu_type_id"] == "NVIDIA H100 80GB HBM3"
        assert kwargs["gpu_count"] == 2
        assert kwargs["min_cpu_count_per_gpu"] == 7
        assert kwargs["min_memory_in_gb_per_gpu"] == 125

    def test_failed_registry_credentials_cleanup_does_not_fail_provisioning(self):
        compute = _compute()
        compute.api_client.create_pod.return_value = {"id": "pod-1"}
        compute.api_client.list_container_registry_credentials.side_effect = RunpodV2ClientError(
            status=429, title="Too Many Requests", detail="Rate limit exceeded"
        )

        jpd = _run_job(compute, _gpu_offer())

        assert jpd.instance_id == "pod-1"
        compute.api_client.terminate_pod.assert_not_called()

    def test_encodes_provider_ref_in_pod_name(self):
        compute = _compute()
        compute.api_client.create_pod.return_value = {"id": "pod-1"}
        job = _job()
        job.job_submissions = [MagicMock(provider_ref="abcdef123456")]

        _run_job(compute, _gpu_offer(), job=job)

        pod_name = compute.api_client.create_pod.call_args.kwargs["name"]
        assert parse_provider_ref_from_name(pod_name) == "abcdef123456"


class TestRunpodComputeRunJobs:
    def test_sets_internal_ip_from_cluster_ip(self):
        compute = _compute()
        compute.api_client.create_cluster.return_value = {"id": "cluster-1", "name": "test"}
        compute.api_client.list_cluster_pods.return_value = [
            _pod("pod-1", cluster_ip="10.65.0.2"),
            _pod("pod-2", is_cluster_pod=True),
        ]

        cgpd = _run_jobs(compute, _cluster_offer([2, 4]), job_count=2)

        assert cgpd.compute_group_id == "cluster-1"
        assert [jpd.instance_id for jpd in cgpd.job_provisioning_datas] == ["pod-1", "pod-2"]
        assert [jpd.internal_ip for jpd in cgpd.job_provisioning_datas] == ["10.65.0.2", None]

    def test_deletes_cluster_if_pod_count_mismatch(self):
        compute = _compute()
        compute.api_client.create_cluster.return_value = {"id": "cluster-1", "name": "test"}
        compute.api_client.list_cluster_pods.return_value = [_pod("pod-1", is_cluster_pod=True)]

        with pytest.raises(ComputeError, match="Expected 2 pods"):
            _run_jobs(compute, _cluster_offer([2, 4]), job_count=2)

        compute.api_client.delete_cluster.assert_called_once_with("cluster-1")

    def test_deletes_cluster_if_listing_pods_fails(self):
        compute = _compute()
        compute.api_client.create_cluster.return_value = {"id": "cluster-1", "name": "test"}
        error = RunpodV2ClientError(status=429, title="Too Many Requests", detail="-")
        compute.api_client.list_cluster_pods.side_effect = error

        with pytest.raises(RunpodV2ClientError):
            _run_jobs(compute, _cluster_offer([2, 4]), job_count=2)

        compute.api_client.delete_cluster.assert_called_once_with("cluster-1")

    def test_raises_original_error_if_cluster_deletion_fails(self):
        compute = _compute()
        compute.api_client.create_cluster.return_value = {"id": "cluster-1", "name": "test"}
        compute.api_client.list_cluster_pods.return_value = []
        compute.api_client.delete_cluster.side_effect = RuntimeError("delete failed")

        with pytest.raises(ComputeError, match="Expected 2 pods"):
            _run_jobs(compute, _cluster_offer([2, 4]), job_count=2)


class TestRunpodComputeUpdateProvisioningData:
    def _update(self, compute: RunpodCompute, jpd: JobProvisioningData) -> None:
        compute.update_provisioning_data(
            provisioning_data=jpd,
            project_ssh_public_key=PROJECT_SSH_PUBLIC_KEY,
            project_ssh_private_key="private-key",
        )

    def test_sets_hostname_and_ssh_port(self):
        compute = _compute()
        compute.api_client.get_pod.return_value = _pod(ports=SSH_PORTS)
        jpd = get_job_provisioning_data(backend=BackendType.RUNPOD, hostname=None)

        self._update(compute, jpd)

        assert jpd.hostname == "203.0.113.10"
        assert jpd.ssh_port == 40022

    def test_waits_for_runtime(self):
        compute = _compute()
        compute.api_client.get_pod.return_value = _pod(ports=None)
        jpd = get_job_provisioning_data(backend=BackendType.RUNPOD, hostname=None)

        self._update(compute, jpd)

        assert jpd.hostname is None

    def test_cluster_pod_waits_for_cluster_ip(self):
        compute = _compute()
        compute.api_client.get_pod.return_value = _pod(ports=SSH_PORTS, is_cluster_pod=True)
        jpd = get_job_provisioning_data(
            backend=BackendType.RUNPOD, hostname=None, internal_ip=None
        )

        self._update(compute, jpd)

        assert jpd.hostname is None
        assert jpd.internal_ip is None

    def test_cluster_pod_sets_internal_ip(self):
        compute = _compute()
        compute.api_client.get_pod.return_value = _pod(ports=SSH_PORTS, cluster_ip="10.65.0.3")
        jpd = get_job_provisioning_data(
            backend=BackendType.RUNPOD, hostname=None, internal_ip=None
        )

        self._update(compute, jpd)

        assert jpd.hostname == "203.0.113.10"
        assert jpd.ssh_port == 40022
        assert jpd.internal_ip == "10.65.0.3"


def _listed_pod(
    pod_id: str,
    *,
    name: str,
    status: str = "RUNNING",
    data_center_id: Optional[str] = "EU-RO-1",
    created_at: str = "2026-10-23T10:00:00Z",
) -> dict:
    pod = _pod(pod_id)
    pod["status"] = status
    pod["name"] = name
    pod["dataCenterId"] = data_center_id
    pod["createdAt"] = created_at
    return pod


class TestRunpodComputeListResourceGroups:
    def test_lists_pods_with_provider_ref(self):
        compute = _compute()
        compute.api_client.list_pods.return_value = [
            _listed_pod("pod-1", name="dstack-main-test-job-0-abcdef123456wxyz"),
        ]

        listing = compute.list_resource_groups()

        assert listing.failures == []
        assert listing.resource_groups == [
            ListedResourceGroup(
                backend=BackendType.RUNPOD,
                owner_type=OwnerType.INSTANCE,
                provider_ref="abcdef123456",
                primary_id="pod-1",
                region="EU-RO-1",
                created_at=datetime(2026, 10, 23, 10, 0, tzinfo=timezone.utc),
                description="pod pod-1",
                backend_data=None,
            )
        ]

    def test_skips_pods_without_provider_ref(self):
        compute = _compute()
        compute.api_client.list_pods.return_value = [
            _listed_pod("pod-1", name="dstack-main-test-job-0-abcdefgh"),
            _listed_pod("pod-2", name="my-pod"),
        ]

        assert compute.list_resource_groups().resource_groups == []

    def test_skips_terminated_pods(self):
        compute = _compute()
        compute.api_client.list_pods.return_value = [
            _listed_pod(
                "pod-1", name="dstack-main-test-job-0-abcdef123456wxyz", status="TERMINATED"
            ),
        ]

        assert compute.list_resource_groups().resource_groups == []

    def test_unparsable_created_at(self):
        compute = _compute()
        compute.api_client.list_pods.return_value = [
            _listed_pod(
                "pod-1", name="dstack-main-test-job-0-abcdef123456wxyz", created_at="invalid"
            ),
        ]

        [group] = compute.list_resource_groups().resource_groups

        assert group.created_at is None


class TestRunpodComputeDeleteResourceGroup:
    def _group(self, primary_id: Optional[str]) -> ListedResourceGroup:
        return ListedResourceGroup(
            backend=BackendType.RUNPOD,
            owner_type=OwnerType.INSTANCE,
            provider_ref="abcdef123456",
            primary_id=primary_id,
            region="EU-RO-1",
            created_at=None,
            description="pod pod-1",
            backend_data=None,
        )

    def test_terminates_pod(self):
        compute = _compute()

        compute.delete_resource_group(self._group("pod-1"))

        compute.api_client.terminate_pod.assert_called_once_with("pod-1")

    def test_pod_already_deleted(self):
        compute = _compute()
        compute.api_client.terminate_pod.return_value = False

        compute.delete_resource_group(self._group("pod-1"))

        compute.api_client.terminate_pod.assert_called_once_with("pod-1")
