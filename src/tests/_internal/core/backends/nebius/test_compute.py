import json
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Callable, Optional
from unittest.mock import Mock

import pytest
from grpc import StatusCode
from nebius.aio.service_error import RequestError, RequestStatusExtended
from nebius.api.nebius.billing.v1 import PricingPolicy, PricingPolicyStatus
from nebius.api.nebius.common.v1 import ResourceMetadata
from nebius.api.nebius.compute.v1 import (
    Disk,
    DiskStatus,
    Instance,
    InstanceSpec,
    InstanceStatus,
    ResourcesSpec,
)

from dstack._internal.core.backends.nebius import compute as compute_module
from dstack._internal.core.backends.nebius.compute import NebiusCompute
from dstack._internal.core.backends.nebius.models import (
    NebiusConfig,
    NebiusServiceAccountCreds,
)
from dstack._internal.core.errors import NotYetTerminated
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.backends.orphans import ListedResourceGroup, OwnerType
from dstack._internal.core.models.instances import (
    Gpu,
    InstanceAvailability,
    InstanceOffer,
    InstanceType,
    Resources,
)


def make_compute() -> NebiusCompute:
    return NebiusCompute(
        NebiusConfig(
            creds=NebiusServiceAccountCreds(
                service_account_id="service-account-id",
                public_key_id="public-key-id",
                private_key_content="private-key",
            )
        )
    )


def make_offer(
    price: float, spot: bool, is_preemptible_flat_rate: bool, gpu_count: int = 8
) -> InstanceOffer:
    return InstanceOffer(
        backend=BackendType.NEBIUS,
        instance=InstanceType(
            name=f"gpu-h100-sxm {gpu_count}gpu-128vcpu-1600gb",
            resources=Resources(
                cpus=128,
                memory_mib=1600 * 1024,
                gpus=[Gpu(name="H100", memory_mib=80 * 1024)] * gpu_count,
                spot=spot,
            ),
        ),
        region="eu-north1",
        price=price,
        backend_data={
            "fabrics": ["fabric-2"],
            "is_preemptible_flat_rate": is_preemptible_flat_rate,
        },
    )


class TestGetAllOffersWithAvailability:
    @pytest.fixture(autouse=True)
    def _mock_region_to_project_id(self, mocker):
        mocker.patch.object(NebiusCompute, "_region_to_project_id", {"eu-north1": "project-id"})

    @pytest.mark.parametrize(
        ("price", "gpu_count", "expected_price"),
        [
            (1.23, 1, 1.23),
            (1.2, 1, 1.2),
            (1.2341, 1, 1.235),
            (1.2349, 1, 1.235),
            (1.2350001, 1, 1.236),
            (0.0001, 1, 0.001),
            (2.007, 1, 2.007),
            (9.84, 8, 9.84),
            (1.23, 8, 1.232),
            (1.2341, 0, 1.235),
        ],
    )
    def test_rounds_spot_price_up_to_3_decimal_places_per_gpu(
        self, mocker, price, gpu_count, expected_price
    ):
        mocker.patch.object(
            compute_module,
            "get_catalog_offers",
            return_value=[
                make_offer(price, spot=True, is_preemptible_flat_rate=False, gpu_count=gpu_count)
            ],
        )

        offers = make_compute().get_all_offers_with_availability(unallocated_resources=False)

        assert len(offers) == 1
        assert offers[0].price == expected_price
        assert offers[0].availability == InstanceAvailability.UNKNOWN

    def test_keeps_on_demand_price_as_is(self, mocker):
        mocker.patch.object(
            compute_module,
            "get_catalog_offers",
            return_value=[make_offer(1.2341, spot=False, is_preemptible_flat_rate=False)],
        )

        offers = make_compute().get_all_offers_with_availability(unallocated_resources=False)

        assert offers[0].price == 1.2341

    def test_keeps_flat_rate_spot_price_as_is(self, mocker):
        mocker.patch.object(
            compute_module,
            "get_catalog_offers",
            return_value=[make_offer(1.2341, spot=True, is_preemptible_flat_rate=True)],
        )

        offers = make_compute().get_all_offers_with_availability(unallocated_resources=False)

        assert offers[0].price == 1.2341


PROVIDER_REF = "abcdef123456"
CREATED_AT = datetime(2026, 10, 1, tzinfo=timezone.utc)


def make_name(provider_ref: str = PROVIDER_REF, suffix: str = "a1b2") -> str:
    return f"dstack-main-fleet-0-{provider_ref}{suffix}"


def make_labels(name: str, provider_ref: str = PROVIDER_REF) -> dict[str, str]:
    return {
        "owner": "dstack",
        "dstack_provider_ref": provider_ref,
        "dstack_provider_name": name,
    }


def make_metadata(
    resource_id: str, name: str, labels: Optional[dict[str, str]], created_at: datetime
) -> ResourceMetadata:
    return ResourceMetadata(id=resource_id, name=name, labels=labels or {}, created_at=created_at)


def make_disk(
    disk_id: str = "disk-1",
    name: Optional[str] = None,
    labels: Optional[dict[str, str]] = None,
    state: DiskStatus.State = DiskStatus.State.READY,
    created_at: datetime = CREATED_AT,
) -> Disk:
    name = name or make_name()
    return Disk(
        metadata=make_metadata(disk_id, name, labels, created_at),
        status=DiskStatus(state=state),
    )


def make_pricing_policy(
    pricing_policy_id: str = "pricingpolicy-1",
    name: Optional[str] = None,
    state: PricingPolicyStatus.State = PricingPolicyStatus.State.STATE_ACTIVE,
    created_at: datetime = CREATED_AT,
) -> PricingPolicy:
    # Nebius drops labels of pricing policies
    return PricingPolicy(
        metadata=make_metadata(pricing_policy_id, name or make_name(), None, created_at),
        status=PricingPolicyStatus(state=state),
    )


def make_instance(
    instance_id: str = "instance-1",
    name: Optional[str] = None,
    labels: Optional[dict[str, str]] = None,
    state: InstanceStatus.InstanceState = InstanceStatus.InstanceState.RUNNING,
    created_at: datetime = CREATED_AT,
) -> Instance:
    name = name or make_name()
    return Instance(
        metadata=make_metadata(instance_id, name, labels, created_at),
        spec=InstanceSpec(resources=ResourcesSpec(platform="cpu-d3", preset="2vcpu-8gb")),
        status=InstanceStatus(state=state),
    )


def make_request_error(code: StatusCode) -> RequestError:
    return RequestError(
        RequestStatusExtended(
            code=code,
            message="error",
            details=[],
            service_errors=[],
            request_id="",
            trace_id="",
        )
    )


def make_resource_group(
    instance_id: Optional[str] = None,
    disk_id: Optional[str] = None,
    pricing_policy_id: Optional[str] = None,
    instance_is_owner: bool = True,
) -> ListedResourceGroup:
    return ListedResourceGroup(
        backend=BackendType.NEBIUS,
        owner_type=OwnerType.INSTANCE,
        provider_ref=PROVIDER_REF,
        primary_id=instance_id if instance_is_owner else None,
        region="eu-north1",
        created_at=CREATED_AT,
        description="",
        backend_data=json.dumps(
            {
                "instance_id": instance_id,
                "disk_id": disk_id,
                "pricing_policy_id": pricing_policy_id,
            }
        ),
    )


class TestListResourceGroups:
    @pytest.fixture(autouse=True)
    def _mock_sdk(self, mocker):
        mocker.patch.object(NebiusCompute, "_sdk", Mock())
        mocker.patch.object(NebiusCompute, "_region_to_project_id", {"eu-north1": "project-id"})

    @pytest.fixture
    def mock_listings(self, mocker):
        def mock(
            disks: Optional[list[Disk]] = None,
            pricing_policies: Optional[list[PricingPolicy]] = None,
            instances: Optional[list[Instance]] = None,
            instances_side_effect: Optional[Callable[..., list[Instance]]] = None,
        ) -> None:
            resources = compute_module.resources
            mocker.patch.object(resources, "list_disks", return_value=disks or [])
            mocker.patch.object(
                resources, "list_pricing_policies", return_value=pricing_policies or []
            )
            mocker.patch.object(
                resources,
                "list_instances",
                return_value=instances or [],
                side_effect=instances_side_effect,
            )

        return mock

    def test_groups_instance_with_its_disk_and_pricing_policy(self, mock_listings):
        name = make_name()
        mock_listings(
            disks=[make_disk(name=name, labels=make_labels(name))],
            pricing_policies=[make_pricing_policy(name=name)],
            instances=[make_instance(name=name, labels=make_labels(name))],
        )

        listing = make_compute().list_resource_groups()

        assert listing.failures == []
        assert len(listing.resource_groups) == 1
        group = listing.resource_groups[0]
        assert group.provider_ref == PROVIDER_REF
        assert group.primary_id == "instance-1"
        assert group.region == "eu-north1"
        assert group.created_at == CREATED_AT
        assert json.loads(group.backend_data or "") == {
            "instance_id": "instance-1",
            "disk_id": "disk-1",
            "pricing_policy_id": "pricingpolicy-1",
        }

    def test_lists_leftovers_without_owner(self, mock_listings):
        name = make_name()
        mock_listings(
            disks=[make_disk(name=name, labels=make_labels(name), created_at=CREATED_AT)],
            pricing_policies=[
                make_pricing_policy(
                    name=name, created_at=datetime(2026, 10, 2, tzinfo=timezone.utc)
                )
            ],
        )

        listing = make_compute().list_resource_groups()

        assert len(listing.resource_groups) == 1
        group = listing.resource_groups[0]
        assert group.primary_id is None
        assert group.created_at == CREATED_AT
        assert json.loads(group.backend_data or "") == {
            "instance_id": None,
            "disk_id": "disk-1",
            "pricing_policy_id": "pricingpolicy-1",
        }

    def test_keeps_id_of_instance_being_deleted_without_owner(self, mock_listings):
        name = make_name()
        mock_listings(
            disks=[make_disk(name=name, labels=make_labels(name))],
            instances=[
                make_instance(
                    name=name,
                    labels=make_labels(name),
                    state=InstanceStatus.InstanceState.DELETING,
                )
            ],
        )

        listing = make_compute().list_resource_groups()

        assert len(listing.resource_groups) == 1
        group = listing.resource_groups[0]
        assert group.primary_id is None
        assert json.loads(group.backend_data or "")["instance_id"] == "instance-1"

    def test_skips_resources_being_deleted(self, mock_listings):
        name = make_name()
        mock_listings(
            disks=[
                make_disk(name=name, labels=make_labels(name), state=DiskStatus.State.DELETING)
            ],
            pricing_policies=[
                make_pricing_policy(name=name, state=PricingPolicyStatus.State.STATE_DELETING)
            ],
            instances=[
                make_instance(
                    name=name,
                    labels=make_labels(name),
                    state=InstanceStatus.InstanceState.DELETING,
                )
            ],
        )

        listing = make_compute().list_resource_groups()

        assert listing.resource_groups == []

    def test_groups_attempts_with_same_provider_ref_separately(self, mock_listings):
        name_1 = make_name(suffix="aaaa")
        name_2 = make_name(suffix="bbbb")
        mock_listings(
            disks=[
                make_disk("disk-1", name=name_1, labels=make_labels(name_1)),
                make_disk("disk-2", name=name_2, labels=make_labels(name_2)),
            ],
            instances=[make_instance(name=name_2, labels=make_labels(name_2))],
        )

        listing = make_compute().list_resource_groups()

        groups = {g.primary_id: g for g in listing.resource_groups}
        assert set(groups) == {None, "instance-1"}
        assert json.loads(groups[None].backend_data or "")["disk_id"] == "disk-1"
        assert json.loads(groups["instance-1"].backend_data or "")["disk_id"] == "disk-2"

    def test_skips_resources_without_valid_provider_ref(self, mock_listings):
        name = make_name()
        mock_listings(
            disks=[
                make_disk("disk-unlabeled", name=name, labels={"owner": "dstack"}),
                make_disk(
                    "disk-invalid",
                    name=name,
                    labels=make_labels(name, provider_ref="INVALID"),
                ),
                make_disk(
                    "disk-without-name",
                    name=name,
                    labels={"dstack_provider_ref": PROVIDER_REF},
                ),
            ],
            pricing_policies=[
                make_pricing_policy("pricingpolicy-old", name="dstack-main-fleet-0-ab12cd34"),
                make_pricing_policy("pricingpolicy-foreign", name="my-policy"),
            ],
        )

        listing = make_compute().list_resource_groups()

        assert listing.resource_groups == []

    def test_reports_failed_region(self, mocker, mock_listings):
        mocker.patch.object(
            NebiusCompute,
            "_region_to_project_id",
            {"eu-north1": "project-1", "us-central1": "project-2"},
        )

        def list_instances(sdk, project_id: str) -> list[Instance]:
            if project_id == "project-2":
                raise make_request_error(StatusCode.UNAVAILABLE)
            return []

        name = make_name()
        mock_listings(
            disks=[make_disk(name=name, labels=make_labels(name))],
            instances_side_effect=list_instances,
        )

        listing = make_compute().list_resource_groups()

        assert [g.region for g in listing.resource_groups] == ["eu-north1"]
        assert [f.region for f in listing.failures] == ["us-central1"]


class TestDeleteResourceGroup:
    @pytest.fixture(autouse=True)
    def _mock_sdk(self, mocker):
        mocker.patch.object(NebiusCompute, "_sdk", Mock())

    @pytest.fixture
    def resources(self, mocker):
        resources = SimpleNamespace(
            **{
                name: mocker.patch.object(compute_module.resources, name)
                for name in [
                    "get_instance",
                    "delete_instance",
                    "delete_disk",
                    "get_pricing_policy",
                    "delete_pricing_policy",
                ]
            }
        )
        resources.get_instance.side_effect = make_request_error(StatusCode.NOT_FOUND)
        resources.get_pricing_policy.return_value = make_pricing_policy()
        return resources

    def test_deletes_instance_first(self, resources):
        resources.get_instance.side_effect = None
        resources.get_instance.return_value = make_instance()
        group = make_resource_group("instance-1", "disk-1", "pricingpolicy-1")

        with pytest.raises(NotYetTerminated):
            make_compute().delete_resource_group(group)

        resources.delete_instance.assert_called_once()
        resources.delete_disk.assert_not_called()
        resources.delete_pricing_policy.assert_not_called()

    def test_waits_for_instance_being_deleted(self, resources):
        resources.get_instance.side_effect = None
        resources.get_instance.return_value = make_instance(
            state=InstanceStatus.InstanceState.DELETING
        )
        group = make_resource_group(
            "instance-1", "disk-1", "pricingpolicy-1", instance_is_owner=False
        )

        with pytest.raises(NotYetTerminated):
            make_compute().delete_resource_group(group)

        resources.delete_instance.assert_not_called()
        resources.delete_disk.assert_not_called()

    def test_deletes_disk_and_pricing_policy_once_instance_is_gone(self, resources):
        group = make_resource_group("instance-1", "disk-1", "pricingpolicy-1")

        make_compute().delete_resource_group(group)

        resources.delete_disk.assert_called_once_with(NebiusCompute._sdk, "disk-1")
        resources.delete_pricing_policy.assert_called_once_with(
            NebiusCompute._sdk, "pricingpolicy-1"
        )

    def test_waits_for_pricing_policy_being_created(self, resources):
        resources.get_pricing_policy.return_value = make_pricing_policy(
            state=PricingPolicyStatus.State.STATE_CREATING
        )
        group = make_resource_group(None, None, "pricingpolicy-1")

        with pytest.raises(NotYetTerminated):
            make_compute().delete_resource_group(group)

        resources.delete_pricing_policy.assert_not_called()
