from datetime import datetime, timezone
from typing import Optional
from unittest.mock import Mock

import pytest
from azure.core.exceptions import HttpResponseError, ODataV4Format, ResourceNotFoundError
from azure.mgmt.compute.models import (
    HardwareProfile,
    ImageReference,
    VirtualMachine,
    VirtualMachineProperties,
)

from dstack._internal import settings
from dstack._internal.core.backends.azure import compute as azure_compute
from dstack._internal.core.backends.azure.compute import (
    AzureCompute,
    VMImageVariant,
    _begin_create_instance,
    _get_image_ref,
)
from dstack._internal.core.backends.azure.models import AzureConfig, AzureDefaultCreds
from dstack._internal.core.errors import ComputeError
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.backends.orphans import ListedResourceGroup, OwnerType
from dstack._internal.core.models.instances import (
    Gpu,
    InstanceConfiguration,
    InstanceType,
    Resources,
)
from dstack._internal.server.testing.common import get_instance_offer_with_availability

RESOURCE_GROUP = "dstack-resources"
PROVIDER_REF = "abc123def456"
TIME_CREATED = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)


class TestVMImageVariant:
    @pytest.mark.parametrize(
        ["instance_type", "expected_variant"],
        [
            [
                InstanceType(
                    name="NV6ads_A10_v5",
                    resources=Resources(
                        cpus=6,
                        memory_mib=55000,
                        gpus=[Gpu(name="NVIDIA A10-4Q", memory_mib=4000)],
                        spot=True,
                    ),
                ),
                VMImageVariant.GRID,
            ],
            [
                InstanceType(
                    name="NV4as_v4",
                    resources=Resources(
                        cpus=4,
                        memory_mib=14000,
                        gpus=[Gpu(name="Tesla T4", memory_mib=16000)],
                        spot=True,
                    ),
                ),
                VMImageVariant.CUDA,
            ],
            [
                InstanceType(
                    name="DS1_v2",
                    resources=Resources(
                        cpus=1,
                        memory_mib=3500,
                        gpus=[],
                        spot=True,
                    ),
                ),
                VMImageVariant.STANDARD,
            ],
        ],
    )
    def test_from_instance_type(
        self, instance_type: InstanceType, expected_variant: VMImageVariant
    ):
        assert VMImageVariant.from_instance_type(instance_type) == expected_variant

    @pytest.mark.parametrize(
        ["variant", "expected_name"],
        [
            [
                VMImageVariant.GRID,
                f"{settings.DSTACK_VM_BASE_IMAGE_PREFIX}dstack-grid-{settings.DSTACK_VM_BASE_IMAGE_VERSION}",
            ],
            [
                VMImageVariant.CUDA,
                f"{settings.DSTACK_VM_BASE_IMAGE_PREFIX}dstack-cuda-{settings.DSTACK_VM_BASE_IMAGE_VERSION}",
            ],
            [
                VMImageVariant.STANDARD,
                f"{settings.DSTACK_VM_BASE_IMAGE_PREFIX}dstack-{settings.DSTACK_VM_BASE_IMAGE_VERSION}",
            ],
        ],
    )
    def test_get_image_name(self, variant: VMImageVariant, expected_name: str):
        assert variant.get_image_name() == expected_name


class TestGetImageRef:
    def test_community_gallery_image(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(settings, "DSTACK_VM_BASE_IMAGE_PREFIX", "")
        compute_client = Mock()
        image_ref = _get_image_ref(compute_client=compute_client, variant=VMImageVariant.GRID)
        assert image_ref.community_gallery_image_id == (
            "/CommunityGalleries/dstack-ebac134d-04b9-4c2b-8b6c-ad3e73904aa7/Images/"
            f"dstack-grid-{settings.DSTACK_VM_BASE_IMAGE_VERSION}"
        )
        assert compute_client.mock_calls == []


class TestBeginCreateInstance:
    def test_raises_compute_error_if_image_not_available(self):
        compute_client = Mock()
        compute_client.virtual_machines.begin_create_or_update.side_effect = _not_found_error(
            "GalleryImageNotFound"
        )
        image_id = "/CommunityGalleries/g/Images/dstack-0.14"
        with pytest.raises(ComputeError, match=f"{image_id} is not available in westeurope"):
            _begin_create_instance(
                **_create_instance_kwargs(
                    compute_client, ImageReference(community_gallery_image_id=image_id)
                )
            )

    def test_reraises_other_not_found_errors(self):
        compute_client = Mock()
        error = _not_found_error("ResourceGroupNotFound")
        compute_client.virtual_machines.begin_create_or_update.side_effect = error
        with pytest.raises(ResourceNotFoundError) as exc_info:
            _begin_create_instance(
                **_create_instance_kwargs(
                    compute_client, ImageReference(community_gallery_image_id="/img")
                )
            )
        assert exc_info.value is error


def _not_found_error(code: str) -> ResourceNotFoundError:
    error = ResourceNotFoundError(code)
    error.error = ODataV4Format({"code": code, "message": code})
    return error


def _create_instance_kwargs(compute_client: Mock, image_reference: ImageReference) -> dict:
    return dict(
        compute_client=compute_client,
        subscription_id="subscription",
        location="westeurope",
        resource_group="resource-group",
        network_security_group="security-group",
        network="network",
        subnet="subnet",
        managed_identity_name=None,
        managed_identity_resource_group=None,
        image_reference=image_reference,
        vm_size="Standard_NV6ads_A10_v5",
        instance_name="instance",
        user_data="",
        ssh_pub_keys=["ssh-ed25519 AAAA"],
        spot=True,
        disk_size=100,
        computer_name="runnervm",
    )


@pytest.fixture
def compute_client() -> Mock:
    return Mock()


@pytest.fixture
def compute(compute_client: Mock) -> AzureCompute:
    compute = AzureCompute(
        AzureConfig(
            tenant_id="tenant",
            subscription_id="subscription",
            resource_group=RESOURCE_GROUP,
            regions=["westeurope"],
            creds=AzureDefaultCreds(),
        ),
        credential=Mock(),
    )
    compute._compute_client = compute_client
    return compute


class TestCreateInstance:
    def test_tags_vm_with_provider_ref(
        self, compute: AzureCompute, monkeypatch: pytest.MonkeyPatch
    ):
        create_instance_and_wait = Mock(return_value=_get_vm("vm-1"))
        monkeypatch.setattr(azure_compute, "_create_instance_and_wait", create_instance_and_wait)
        monkeypatch.setattr(
            azure_compute,
            "get_resource_group_network_subnet_or_error",
            Mock(return_value=(RESOURCE_GROUP, "network", "subnet")),
        )
        monkeypatch.setattr(azure_compute, "_get_image_ref", Mock())
        monkeypatch.setattr(
            azure_compute, "_get_vm_public_private_ips", Mock(return_value=("1.2.3.4", "10.0.0.4"))
        )
        compute.create_instance(
            get_instance_offer_with_availability(backend=BackendType.AZURE, region="westeurope"),
            InstanceConfiguration(
                project_name="project",
                instance_name="instance",
                user="user",
                ssh_keys=[],
                provider_ref=PROVIDER_REF,
            ),
            placement_group=None,
        )
        tags = create_instance_and_wait.call_args.kwargs["tags"]
        assert tags["dstack_provider_ref"] == PROVIDER_REF


class TestListResourceGroups:
    def test_lists_tagged_vms(self, compute: AzureCompute, compute_client: Mock):
        _set_vms(compute_client, [_get_vm("vm-1")])
        listing = compute.list_resource_groups()
        compute_client.virtual_machines.list.assert_called_once_with(
            resource_group_name=RESOURCE_GROUP
        )
        assert listing.failures == []
        assert listing.resource_groups == [
            ListedResourceGroup(
                backend=BackendType.AZURE,
                owner_type=OwnerType.INSTANCE,
                provider_ref=PROVIDER_REF,
                primary_id="vm-1",
                region="westeurope",
                created_at=TIME_CREATED,
                description="VM vm-1 (Standard_D2s_v6, Succeeded)",
                backend_data=None,
            )
        ]

    def test_skips_vms_without_provider_ref(self, compute: AzureCompute, compute_client: Mock):
        _set_vms(compute_client, [_get_vm("vm-1", provider_ref=None)])
        assert compute.list_resource_groups().resource_groups == []

    def test_skips_vms_with_invalid_provider_ref(
        self, compute: AzureCompute, compute_client: Mock
    ):
        _set_vms(compute_client, [_get_vm("vm-1", provider_ref="Invalid-Ref")])
        assert compute.list_resource_groups().resource_groups == []

    def test_skips_vms_being_deleted(self, compute: AzureCompute, compute_client: Mock):
        _set_vms(
            compute_client,
            [_get_vm("vm-1", provisioning_state="Deleting"), _get_vm("vm-2")],
        )
        groups = compute.list_resource_groups().resource_groups
        assert [g.primary_id for g in groups] == ["vm-2"]

    def test_raises_compute_error_on_api_error(self, compute: AzureCompute, compute_client: Mock):
        compute_client.virtual_machines.list.side_effect = HttpResponseError("error")
        with pytest.raises(ComputeError):
            compute.list_resource_groups()


class TestDeleteResourceGroup:
    def test_deletes_vm(self, compute: AzureCompute, compute_client: Mock):
        compute.delete_resource_group(_get_resource_group())
        compute_client.virtual_machines.begin_delete.assert_called_once_with(
            resource_group_name=RESOURCE_GROUP, vm_name="vm-1"
        )

    def test_tolerates_deleted_vm(self, compute: AzureCompute, compute_client: Mock):
        compute_client.virtual_machines.begin_delete.side_effect = _not_found_error(
            "ResourceNotFound"
        )
        compute.delete_resource_group(_get_resource_group())

    def test_raises_compute_error_on_api_error(self, compute: AzureCompute, compute_client: Mock):
        compute_client.virtual_machines.begin_delete.side_effect = HttpResponseError("error")
        with pytest.raises(ComputeError):
            compute.delete_resource_group(_get_resource_group())


def _get_vm(
    name: str,
    provider_ref: Optional[str] = PROVIDER_REF,
    provisioning_state: str = "Succeeded",
) -> VirtualMachine:
    tags = {"owner": "dstack"}
    if provider_ref is not None:
        tags["dstack_provider_ref"] = provider_ref
    vm = VirtualMachine(
        location="westeurope",
        tags=tags,
        properties=VirtualMachineProperties(
            hardware_profile=HardwareProfile(vm_size="Standard_D2s_v6")
        ),
    )
    vm.id = f"/subscriptions/subscription/resourceGroups/{RESOURCE_GROUP}/providers/Microsoft.Compute/virtualMachines/{name}"
    vm.name = name
    vm.provisioning_state = provisioning_state
    vm.time_created = TIME_CREATED
    return vm


def _set_vms(compute_client: Mock, vms: list[VirtualMachine]):
    compute_client.virtual_machines.list.return_value = iter(vms)


def _get_resource_group() -> ListedResourceGroup:
    return ListedResourceGroup(
        backend=BackendType.AZURE,
        owner_type=OwnerType.INSTANCE,
        provider_ref=PROVIDER_REF,
        primary_id="vm-1",
        region="westeurope",
        created_at=TIME_CREATED,
        description="VM vm-1",
        backend_data=None,
    )
