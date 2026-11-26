from datetime import datetime, timezone
from typing import Optional
from unittest.mock import MagicMock, patch

import gpuhunt
from gpuhunt.providers.base import OnlineProvider

from dstack._internal.core.backends.base.compute import parse_provider_ref_from_name
from dstack._internal.core.backends.runpod.api_client import RunpodV2ClientError
from dstack._internal.core.backends.runpod.compute import RunpodCompute
from dstack._internal.core.backends.runpod.models import RunpodAPIKeyCreds, RunpodConfig
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.backends.orphans import ListedResourceGroup, OwnerType
from dstack._internal.core.models.instances import (
    InstanceAvailability,
    InstanceOfferWithAvailability,
)
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


def _compute_with_mocked_api_client() -> tuple[RunpodCompute, MagicMock]:
    compute = RunpodCompute(RunpodConfig(creds=RunpodAPIKeyCreds(api_key="test")))
    api_client = MagicMock()
    compute.api_client = api_client
    return compute, api_client


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


def _job() -> MagicMock:
    job = MagicMock()
    job.job_spec.job_name = "test-job-0"
    job.job_spec.image_name = "dstackai/base:latest"
    job.job_spec.registry_auth = None
    return job


def _run() -> MagicMock:
    run = MagicMock()
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
            project_name="main",
            project_ssh_public_key=PROJECT_SSH_PUBLIC_KEY,
            project_ssh_private_key="private-key",
            volumes=[],
            placement_group=None,
            requirements=Requirements(resources=ResourcesSpec()),
            extra_authorized_keys=[],
        )


def _pod(pod_id: str = "pod-1", *, ports: Optional[list[dict]] = None) -> dict:
    return {
        "id": pod_id,
        "status": "RUNNING",
        "runtime": None if ports is None else {"ports": ports},
        "mounts": {},
    }


SSH_PORTS = [
    {"ip": "100.65.0.1", "private": 8080, "public": None, "type": "http"},
    {"ip": "203.0.113.10", "private": 10022, "public": 40022, "type": "tcp"},
]


class _FakeRunpodProvider(OnlineProvider):
    NAME = "runpod"

    def __init__(self, items: list[gpuhunt.CatalogItem]):
        self.items = items
        self.query_filters: list[Optional[gpuhunt.QueryFilter]] = []

    @classmethod
    def from_env(cls) -> "_FakeRunpodProvider":
        raise NotImplementedError

    def get(
        self,
        query_filter: Optional[gpuhunt.QueryFilter] = None,
        balance_resources: bool = True,
        apply_filter: bool = False,
    ) -> list[gpuhunt.CatalogItem]:
        self.query_filters.append(query_filter)
        return self.items


def _gpu_item(location: str = "EU-RO-1") -> gpuhunt.CatalogItem:
    return gpuhunt.CatalogItem(
        provider="runpod",
        instance_name="NVIDIA H100 80GB HBM3",
        location=location,
        price=4.39,
        cpu=16,
        memory=251,
        gpu_vendor=gpuhunt.AcceleratorVendor.NVIDIA,
        gpu_count=1,
        gpu_name="H100",
        gpu_memory=80,
        spot=False,
        disk_size=None,
    )


def _cpu_item(vcpu: int, max_disk_size: float) -> gpuhunt.CatalogItem:
    return gpuhunt.CatalogItem(
        provider="runpod",
        instance_name=f"cpu3c-{vcpu}-{vcpu * 2}",
        location="EU-RO-1",
        price=0.03 * vcpu,
        cpu=vcpu,
        memory=vcpu * 2,
        gpu_count=0,
        gpu_name=None,
        gpu_memory=None,
        spot=False,
        disk_size=max_disk_size,
    )


def _get_offers(
    items: list[gpuhunt.CatalogItem], resources: dict, regions: Optional[list[str]] = None
) -> tuple[list[InstanceOfferWithAvailability], _FakeRunpodProvider]:
    compute = RunpodCompute(RunpodConfig(creds=RunpodAPIKeyCreds(api_key="test"), regions=regions))
    provider = _FakeRunpodProvider(items)
    compute.catalog = gpuhunt.Catalog(balance_resources=False, auto_reload=False)
    compute.catalog.add_provider(provider)
    requirements = Requirements(resources=ResourcesSpec.model_validate(resources))
    offers = list(compute.get_offers(requirements, full_offers=False, unallocated_resources=False))
    return offers, provider


class TestRunpodComputeGetOffers:
    def test_queries_catalog_with_requirements(self):
        _, provider = _get_offers(
            [], {"cpu": "16..", "memory": "64GB..", "gpu": "H100:2..4", "disk": "50GB"}
        )

        [query_filter] = provider.query_filters
        assert query_filter is not None
        assert (query_filter.min_cpu, query_filter.min_memory) == (16, 64)
        assert (query_filter.min_gpu_count, query_filter.max_gpu_count) == (2, 4)
        assert query_filter.gpu_name == ["H100"]
        # Disks are fitted by the compute
        assert (query_filter.min_disk_size, query_filter.max_disk_size) == (None, None)

    def test_offers_are_available(self):
        offers, _ = _get_offers([_gpu_item()], {"gpu": "1"})

        [offer] = offers
        assert offer.availability == InstanceAvailability.AVAILABLE
        assert offer.region == "EU-RO-1"
        assert (offer.instance.resources.cpus, offer.instance.resources.memory_mib) == (
            16,
            251 * 1024,
        )

    def test_fits_gpu_offer_disk_to_requirements(self):
        offers, _ = _get_offers([_gpu_item()], {"gpu": "1", "disk": "500GB.."})

        [offer] = offers
        assert offer.instance.resources.disk.size_mib == 500 * 1024

    def test_fits_cpu_offer_disk_to_requirements_within_max_disk_size(self):
        items = [_cpu_item(vcpu=2, max_disk_size=20), _cpu_item(vcpu=8, max_disk_size=80)]

        offers, _ = _get_offers(items, {"gpu": 0, "disk": "50GB"})

        [offer] = offers
        assert offer.instance.name == "cpu3c-8-16"
        assert offer.instance.resources.disk.size_mib == 50 * 1024

    def test_filters_by_configured_regions(self):
        items = [_gpu_item("EU-RO-1"), _gpu_item("US-KS-2")]

        offers, _ = _get_offers(items, {"gpu": "1"}, regions=["US-KS-2"])

        assert [o.region for o in offers] == ["US-KS-2"]


class TestRunpodComputeRunJob:
    def test_requests_per_gpu_minimums_rounded_down(self):
        compute, api_client = _compute_with_mocked_api_client()
        api_client.create_pod.return_value = {"id": "pod-1"}

        jpd = _run_job(compute, _gpu_offer(gpu_count=2, cpu_count=15, memory_gib=251))

        assert jpd.instance_id == "pod-1"
        kwargs = api_client.create_pod.call_args.kwargs
        assert kwargs["cloud"] == "SECURE"
        assert kwargs["data_center_ids"] == ["EU-RO-1"]
        assert kwargs["gpu_type_id"] == "NVIDIA H100 80GB HBM3"
        assert kwargs["gpu_count"] == 2
        assert kwargs["min_cpu_count_per_gpu"] == 7
        assert kwargs["min_memory_in_gb_per_gpu"] == 125

    def test_failed_registry_credentials_cleanup_does_not_fail_provisioning(self):
        compute, api_client = _compute_with_mocked_api_client()
        api_client.create_pod.return_value = {"id": "pod-1"}
        api_client.list_container_registry_credentials.side_effect = RunpodV2ClientError(
            status=429, title="Too Many Requests", detail="Rate limit exceeded"
        )

        jpd = _run_job(compute, _gpu_offer())

        assert jpd.instance_id == "pod-1"
        api_client.terminate_pod.assert_not_called()

    def test_encodes_provider_ref_in_pod_name(self):
        compute, api_client = _compute_with_mocked_api_client()
        api_client.create_pod.return_value = {"id": "pod-1"}
        job = _job()
        job.job_submissions = [MagicMock(provider_ref="abcdef123456")]

        _run_job(compute, _gpu_offer(), job=job)

        pod_name = api_client.create_pod.call_args.kwargs["name"]
        assert parse_provider_ref_from_name(pod_name) == "abcdef123456"

    def test_cpu_offer(self):
        compute, api_client = _compute_with_mocked_api_client()
        api_client.create_pod.return_value = {"id": "pod-1"}
        offer = get_instance_offer_with_availability(
            backend=BackendType.RUNPOD,
            region="EU-RO-1",
            cpu_count=16,
            memory_gib=32,
            disk_gib=50,
            instance_type="cpu3c-16-32",
        )

        _run_job(compute, offer)

        kwargs = api_client.create_pod.call_args.kwargs
        assert kwargs["cloud"] == "SECURE"
        assert kwargs["data_center_ids"] == ["EU-RO-1"]
        assert kwargs["cpu_type_id"] == "cpu3c"
        assert kwargs["cpu_count"] == 16
        assert kwargs["container_disk_in_gb"] == 50
        assert kwargs["gpu_type_id"] is None


class TestRunpodComputeUpdateProvisioningData:
    def _update(self, compute: RunpodCompute, jpd: JobProvisioningData) -> None:
        compute.update_provisioning_data(
            provisioning_data=jpd,
            project_ssh_public_key=PROJECT_SSH_PUBLIC_KEY,
            project_ssh_private_key="private-key",
        )

    def test_sets_hostname_and_ssh_port(self):
        compute, api_client = _compute_with_mocked_api_client()
        api_client.get_pod.return_value = _pod(ports=SSH_PORTS)
        jpd = get_job_provisioning_data(backend=BackendType.RUNPOD, hostname=None)

        self._update(compute, jpd)

        assert jpd.hostname == "203.0.113.10"
        assert jpd.ssh_port == 40022

    def test_waits_for_runtime(self):
        compute, api_client = _compute_with_mocked_api_client()
        api_client.get_pod.return_value = _pod(ports=None)
        jpd = get_job_provisioning_data(backend=BackendType.RUNPOD, hostname=None)

        self._update(compute, jpd)

        assert jpd.hostname is None


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
        compute, api_client = _compute_with_mocked_api_client()
        api_client.list_pods.return_value = [
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
        compute, api_client = _compute_with_mocked_api_client()
        api_client.list_pods.return_value = [
            _listed_pod("pod-1", name="dstack-main-test-job-0-abcdefgh"),
            _listed_pod("pod-2", name="my-pod"),
        ]

        assert compute.list_resource_groups().resource_groups == []

    def test_skips_terminated_pods(self):
        compute, api_client = _compute_with_mocked_api_client()
        api_client.list_pods.return_value = [
            _listed_pod(
                "pod-1", name="dstack-main-test-job-0-abcdef123456wxyz", status="TERMINATED"
            ),
        ]

        assert compute.list_resource_groups().resource_groups == []

    def test_unparsable_created_at(self):
        compute, api_client = _compute_with_mocked_api_client()
        api_client.list_pods.return_value = [
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
        compute, api_client = _compute_with_mocked_api_client()

        compute.delete_resource_group(self._group("pod-1"))

        api_client.terminate_pod.assert_called_once_with("pod-1")

    def test_pod_already_deleted(self):
        compute, api_client = _compute_with_mocked_api_client()
        api_client.terminate_pod.return_value = False

        compute.delete_resource_group(self._group("pod-1"))

        api_client.terminate_pod.assert_called_once_with("pod-1")
