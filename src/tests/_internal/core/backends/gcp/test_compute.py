import json
from datetime import datetime, timezone
from typing import Optional
from unittest.mock import Mock

import google.api_core.exceptions
import pytest
from google.auth.credentials import AnonymousCredentials
from google.cloud import compute_v1, tpu_v2
from gpuhunt import AcceleratorVendor, CatalogItem

from dstack._internal.core.backends.gcp.compute import GCPCompute
from dstack._internal.core.backends.gcp.models import GCPConfig, GCPDefaultCreds
from dstack._internal.core.errors import ComputeError
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.backends.orphans import ListedResourceGroup, OwnerType

PROJECT_ID = "test-project"
PROVIDER_REF = "abc123def456"
CREATED_AT = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)


def _get_compute(mocker, regions: list[str], tpu: bool = False) -> GCPCompute:
    mocker.patch(
        "dstack._internal.core.backends.gcp.auth.authenticate",
        return_value=(AnonymousCredentials(), None),
    )
    return GCPCompute(
        GCPConfig(project_id=PROJECT_ID, regions=regions, creds=GCPDefaultCreds(), tpu=tpu)
    )


class TestGetAllOffersWithAvailability:
    @pytest.mark.parametrize(
        "tpu_config", [{}, {"tpu": False}, {"tpu": True}], ids=["default", "disabled", "enabled"]
    )
    def test_returns_tpu_offers_only_if_enabled(self, mocker, tpu_config):
        mocker.patch(
            "dstack._internal.core.backends.gcp.auth.authenticate",
            return_value=(AnonymousCredentials(), None),
        )
        compute = GCPCompute(
            GCPConfig(
                project_id="test-project",
                regions=["us-central1"],
                creds=GCPDefaultCreds(),
                **tpu_config,
            )
        )
        mocker.patch.object(compute.regions_client, "list", return_value=[])
        items = [
            CatalogItem(
                provider="gcp",
                instance_name=name,
                location="us-central1-a",
                price=1.0,
                cpu=4,
                memory=16,
                gpu_count=int(vendor is not None),
                gpu_vendor=vendor,
                gpu_name=gpu_name,
                gpu_memory=16 if vendor is not None else None,
                spot=False,
                disk_size=None,
            )
            for name, vendor, gpu_name in [
                ("n2-standard-4", None, None),
                ("g2-standard-4", AcceleratorVendor.NVIDIA, "L4"),
                ("v5litepod-8", AcceleratorVendor.GOOGLE, "v5litepod-8"),
            ]
        ]
        mocker.patch("gpuhunt.default_catalog").return_value.query.return_value = items

        offers = compute.get_all_offers_with_availability(unallocated_resources=False)

        expected_names = ["n2-standard-4", "g2-standard-4"]
        if tpu_config.get("tpu"):
            expected_names.append("v5litepod-8")
        assert [offer.instance.name for offer in offers] == expected_names


def _get_vm(
    name: str, provider_ref: Optional[str] = PROVIDER_REF, status: str = "RUNNING"
) -> compute_v1.Instance:
    labels = {"owner": "dstack"}
    if provider_ref is not None:
        labels["dstack_provider_ref"] = provider_ref
    return compute_v1.Instance(
        name=name,
        machine_type=f"https://www.googleapis.com/compute/v1/projects/{PROJECT_ID}/zones/us-central1-a/machineTypes/g2-standard-4",
        status=status,
        creation_timestamp="2026-01-01T04:00:00.000-08:00",
        labels=labels,
    )


def _get_vm_pages(
    instances_by_zone: dict[str, list[compute_v1.Instance]],
    unreachable_zones: tuple[str, ...] = (),
) -> Mock:
    items = {}
    for zone, instances in instances_by_zone.items():
        items[f"zones/{zone}"] = compute_v1.InstancesScopedList(instances=instances)
    for zone in unreachable_zones:
        items[f"zones/{zone}"] = compute_v1.InstancesScopedList(
            warning=compute_v1.Warning(code="UNREACHABLE")
        )
    return Mock(pages=[compute_v1.InstanceAggregatedList(items=items)])


def _get_tpu_node(
    node_id: str, zone: str = "us-central1-a", state=tpu_v2.Node.State.READY
) -> tpu_v2.Node:
    node = tpu_v2.Node(
        name=f"projects/{PROJECT_ID}/locations/{zone}/nodes/{node_id}",
        accelerator_type="v5litepod-8",
        state=state,
        labels={"owner": "dstack", "dstack_provider_ref": PROVIDER_REF},
        create_time=CREATED_AT,
    )
    return node


def _get_resource_group(is_tpu: bool = False) -> ListedResourceGroup:
    return ListedResourceGroup(
        backend=BackendType.GCP,
        owner_type=OwnerType.INSTANCE,
        provider_ref=PROVIDER_REF,
        primary_id="vm-1",
        region="us-central1",
        created_at=CREATED_AT,
        description="instance vm-1",
        backend_data=json.dumps({"zone": "us-central1-a", "is_tpu": is_tpu}),
    )


class TestListResourceGroups:
    def test_lists_labeled_vm(self, mocker):
        compute = _get_compute(mocker, regions=["us-central1"])
        aggregated_list = mocker.patch.object(
            compute.instances_client,
            "aggregated_list",
            return_value=_get_vm_pages({"us-central1-a": [_get_vm("vm-1")]}),
        )

        listing = compute.list_resource_groups()

        request = aggregated_list.call_args.kwargs["request"]
        assert request.project == PROJECT_ID
        assert request.filter == "labels.dstack_provider_ref:*"
        assert listing.failures == []
        assert len(listing.resource_groups) == 1
        group = listing.resource_groups[0]
        assert group.backend == BackendType.GCP
        assert group.owner_type == OwnerType.INSTANCE
        assert group.provider_ref == PROVIDER_REF
        assert group.primary_id == "vm-1"
        assert group.region == "us-central1"
        assert group.created_at == CREATED_AT
        assert group.description == "instance vm-1 (g2-standard-4, RUNNING)"
        assert json.loads(group.backend_data or "") == {"zone": "us-central1-a", "is_tpu": False}

    def test_skips_vms_without_valid_provider_ref(self, mocker):
        compute = _get_compute(mocker, regions=["us-central1"])
        vms = [_get_vm("vm-1", provider_ref=None), _get_vm("vm-2", provider_ref="Invalid-Ref")]
        mocker.patch.object(
            compute.instances_client,
            "aggregated_list",
            return_value=_get_vm_pages({"us-central1-a": vms}),
        )
        assert compute.list_resource_groups().resource_groups == []

    def test_skips_stopping_vms_and_lists_stopped_ones(self, mocker):
        compute = _get_compute(mocker, regions=["us-central1"])
        vms = [_get_vm("vm-1", status="STOPPING"), _get_vm("vm-2", status="TERMINATED")]
        mocker.patch.object(
            compute.instances_client,
            "aggregated_list",
            return_value=_get_vm_pages({"us-central1-a": vms}),
        )
        groups = compute.list_resource_groups().resource_groups
        assert [g.primary_id for g in groups] == ["vm-2"]

    def test_skips_regions_not_in_config(self, mocker):
        compute = _get_compute(mocker, regions=["us-central1"])
        mocker.patch.object(
            compute.instances_client,
            "aggregated_list",
            return_value=_get_vm_pages(
                {"us-central1-a": [_get_vm("vm-1")], "europe-west4-a": [_get_vm("vm-2")]},
                unreachable_zones=("europe-west4-b",),
            ),
        )
        listing = compute.list_resource_groups()
        assert [g.primary_id for g in listing.resource_groups] == ["vm-1"]
        assert listing.failures == []

    def test_reports_region_with_unreachable_zone_and_lists_other_regions(self, mocker):
        compute = _get_compute(mocker, regions=["us-central1", "europe-west4"])
        mocker.patch.object(
            compute.instances_client,
            "aggregated_list",
            return_value=_get_vm_pages(
                {"us-central1-a": [_get_vm("vm-1")], "europe-west4-a": [_get_vm("vm-2")]},
                unreachable_zones=("europe-west4-b",),
            ),
        )
        listing = compute.list_resource_groups()
        assert [g.primary_id for g in listing.resource_groups] == ["vm-1"]
        assert [(f.backend, f.region) for f in listing.failures] == [
            (BackendType.GCP, "europe-west4")
        ]

    def test_raises_if_all_regions_unreachable(self, mocker):
        compute = _get_compute(mocker, regions=["us-central1"])
        mocker.patch.object(
            compute.instances_client,
            "aggregated_list",
            return_value=_get_vm_pages({}, unreachable_zones=("us-central1-a",)),
        )
        with pytest.raises(ComputeError):
            compute.list_resource_groups()

    def test_raises_compute_error_if_not_permitted(self, mocker):
        compute = _get_compute(mocker, regions=["us-central1"])
        mocker.patch.object(
            compute.instances_client,
            "aggregated_list",
            side_effect=google.api_core.exceptions.Forbidden("Required permission"),
        )
        with pytest.raises(ComputeError, match="compute.instances.list"):
            compute.list_resource_groups()

    @pytest.mark.parametrize("tpu", [False, True], ids=["tpu_disabled", "tpu_enabled"])
    def test_lists_tpu_nodes_only_if_enabled(self, mocker, tpu: bool):
        compute = _get_compute(mocker, regions=["us-central1"], tpu=tpu)
        mocker.patch.object(
            compute.instances_client, "aggregated_list", return_value=_get_vm_pages({})
        )
        list_nodes = mocker.patch.object(
            compute.tpu_client,
            "list_nodes",
            return_value=Mock(
                pages=[
                    tpu_v2.ListNodesResponse(
                        nodes=[
                            _get_tpu_node("tpu-1"),
                            _get_tpu_node("tpu-2", state=tpu_v2.Node.State.DELETING),
                        ]
                    )
                ]
            ),
        )

        groups = compute.list_resource_groups().resource_groups

        if not tpu:
            list_nodes.assert_not_called()
            assert groups == []
            return
        assert (
            list_nodes.call_args.kwargs["request"].parent == f"projects/{PROJECT_ID}/locations/-"
        )
        assert len(groups) == 1
        group = groups[0]
        assert group.primary_id == "tpu-1"
        assert group.region == "us-central1"
        assert group.created_at == CREATED_AT
        assert json.loads(group.backend_data or "") == {"zone": "us-central1-a", "is_tpu": True}

    def test_reports_region_with_unreachable_tpu_location(self, mocker):
        compute = _get_compute(mocker, regions=["us-central1", "europe-west4"], tpu=True)
        mocker.patch.object(
            compute.instances_client,
            "aggregated_list",
            return_value=_get_vm_pages({"us-central1-a": [_get_vm("vm-1")]}),
        )
        mocker.patch.object(
            compute.tpu_client,
            "list_nodes",
            return_value=Mock(
                pages=[
                    tpu_v2.ListNodesResponse(
                        nodes=[_get_tpu_node("tpu-1", zone="europe-west4-a")],
                        unreachable=[f"projects/{PROJECT_ID}/locations/europe-west4-b"],
                    )
                ]
            ),
        )
        listing = compute.list_resource_groups()
        assert [g.primary_id for g in listing.resource_groups] == ["vm-1"]
        assert [f.region for f in listing.failures] == ["europe-west4"]


class TestDeleteResourceGroup:
    def test_deletes_vm(self, mocker):
        compute = _get_compute(mocker, regions=["us-central1"])
        delete = mocker.patch.object(compute.instances_client, "delete")
        compute.delete_resource_group(_get_resource_group())
        delete.assert_called_once_with(project=PROJECT_ID, zone="us-central1-a", instance="vm-1")

    def test_deletes_tpu_node(self, mocker):
        compute = _get_compute(mocker, regions=["us-central1"], tpu=True)
        delete_node = mocker.patch.object(compute.tpu_client, "delete_node")
        compute.delete_resource_group(_get_resource_group(is_tpu=True))
        assert (
            delete_node.call_args.kwargs["request"].name
            == f"projects/{PROJECT_ID}/locations/us-central1-a/nodes/vm-1"
        )

    def test_tolerates_already_deleted_vm(self, mocker):
        compute = _get_compute(mocker, regions=["us-central1"])
        mocker.patch.object(
            compute.instances_client,
            "delete",
            side_effect=google.api_core.exceptions.NotFound("not found"),
        )
        compute.delete_resource_group(_get_resource_group())

    def test_raises_compute_error_on_api_error(self, mocker):
        compute = _get_compute(mocker, regions=["us-central1"])
        mocker.patch.object(
            compute.instances_client,
            "delete",
            side_effect=google.api_core.exceptions.Forbidden("Required permission"),
        )
        with pytest.raises(ComputeError):
            compute.delete_resource_group(_get_resource_group())
