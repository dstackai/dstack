from unittest.mock import Mock

import pytest
from azure.core.exceptions import ODataV4Format, ResourceNotFoundError
from azure.mgmt.compute.models import ImageReference

from dstack._internal import settings
from dstack._internal.core.backends.azure.compute import (
    VMImageVariant,
    _begin_create_instance,
    _get_image_ref,
)
from dstack._internal.core.errors import ComputeError
from dstack._internal.core.models.instances import Gpu, InstanceType, Resources


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
