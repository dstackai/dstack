import pytest

from dstack._internal import settings
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import InstanceType
from dstack._internal.core.models.runs import JobProvisioningData
from dstack._internal.server.services.backends.provisioning import (
    resolve_provisioning_image,
)
from dstack._internal.server.testing.common import get_job_provisioning_data


class TestResolveProvisioningImageName:
    @staticmethod
    def _create_job_provisioning_data_with_instance_type(
        backend: BackendType,
        instance_type: str,
    ) -> JobProvisioningData:
        job_provisioning_data = get_job_provisioning_data(backend=backend)
        job_provisioning_data.instance_type = InstanceType(
            name=instance_type,
            resources=job_provisioning_data.instance_type.resources,
        )
        return job_provisioning_data

    @staticmethod
    def _call_resolve_provisioning_image(
        image_name: str,
        backend: BackendType,
        instance_type: str,
    ) -> str:
        job_provisioning_data = (
            TestResolveProvisioningImageName._create_job_provisioning_data_with_instance_type(
                backend,
                instance_type,
            )
        )
        image_name, _ = resolve_provisioning_image(image_name, None, job_provisioning_data)
        return image_name

    @pytest.mark.parametrize(
        ("suffix", "instance_type"),
        [
            ("-base", "p6-b200.48xlarge"),
            ("-devel", "p5.48xlarge"),
        ],
    )
    def test_patch_aws_efa_instance_with_suffix(self, suffix: str, instance_type: str) -> None:
        image_name = (
            f"{settings.DSTACK_BASE_IMAGE}:{settings.DSTACK_BASE_IMAGE_VERSION}{suffix}"
            f"-ubuntu{settings.DSTACK_BASE_IMAGE_UBUNTU_VERSION}"
        )
        result = self._call_resolve_provisioning_image(
            image_name,
            BackendType.AWS,
            instance_type,
        )
        expected = (
            f"{settings.DSTACK_BASE_IMAGE}:{settings.DSTACK_BASE_IMAGE_VERSION}"
            f"-devel-efa-ubuntu{settings.DSTACK_BASE_IMAGE_UBUNTU_VERSION}"
        )
        assert result == expected

    @pytest.mark.parametrize("suffix", ["-base", "-devel"])
    @pytest.mark.parametrize(
        "instance_type",
        [
            "p5.48xlarge",
            "p5e.48xlarge",
            "p4d.24xlarge",
            "p4de.24xlarge",
            "g6.8xlarge",
            "g6e.8xlarge",
        ],
    )
    def test_patch_all_efa_instance_types(self, instance_type: str, suffix: str) -> None:
        image_name = (
            f"{settings.DSTACK_BASE_IMAGE}:{settings.DSTACK_BASE_IMAGE_VERSION}{suffix}"
            f"-ubuntu{settings.DSTACK_BASE_IMAGE_UBUNTU_VERSION}"
        )
        result = self._call_resolve_provisioning_image(
            image_name,
            BackendType.AWS,
            instance_type,
        )
        expected = (
            f"{settings.DSTACK_BASE_IMAGE}:{settings.DSTACK_BASE_IMAGE_VERSION}"
            f"-devel-efa-ubuntu{settings.DSTACK_BASE_IMAGE_UBUNTU_VERSION}"
        )
        assert result == expected

    @pytest.mark.parametrize("suffix", ["-base", "-devel"])
    @pytest.mark.parametrize(
        "backend",
        [BackendType.GCP, BackendType.AZURE, BackendType.LAMBDA, BackendType.LOCAL],
    )
    @pytest.mark.parametrize(
        "instance_type",
        ["standard-4", "p5.xlarge", "p6.2xlarge", "g6.xlarge"],
    )
    def test_no_patch_non_aws_backends(
        self,
        backend: BackendType,
        suffix: str,
        instance_type: str,
    ) -> None:
        image_name = (
            f"{settings.DSTACK_BASE_IMAGE}:{settings.DSTACK_BASE_IMAGE_VERSION}{suffix}"
            f"-ubuntu{settings.DSTACK_BASE_IMAGE_UBUNTU_VERSION}"
        )
        result = self._call_resolve_provisioning_image(image_name, backend, instance_type)
        assert result == image_name

    @pytest.mark.parametrize("suffix", ["-base", "-devel"])
    @pytest.mark.parametrize(
        "instance_type",
        ["t3.micro", "m5.large", "c5.xlarge", "r5.2xlarge", "m6i.large", "g6.xlarge"],
    )
    def test_no_patch_non_efa_aws_instances(self, instance_type: str, suffix: str) -> None:
        image_name = f"{settings.DSTACK_BASE_IMAGE}:{settings.DSTACK_BASE_IMAGE_VERSION}{suffix}"
        result = self._call_resolve_provisioning_image(
            image_name,
            BackendType.AWS,
            instance_type,
        )
        assert result == image_name

    @pytest.mark.parametrize(
        "instance_type",
        ["p5.xlarge", "p6.2xlarge", "t3.micro", "m5.large"],
    )
    @pytest.mark.parametrize(
        "image_name",
        [
            "ubuntu:20.04",
            "nvidia/cuda:11.8-runtime-ubuntu20.04",
            "python:3.9-slim",
            "custom/image:latest",
            f"{settings.DSTACK_BASE_IMAGE}:{settings.DSTACK_BASE_IMAGE_VERSION}-custom",
            f"{settings.DSTACK_BASE_IMAGE}:{settings.DSTACK_BASE_IMAGE_VERSION}-devel-efa",
            f"{settings.DSTACK_BASE_IMAGE}:{settings.DSTACK_BASE_IMAGE_VERSION}",
        ],
    )
    def test_no_patch_other_images(self, instance_type: str, image_name: str) -> None:
        result = self._call_resolve_provisioning_image(
            image_name,
            BackendType.AWS,
            instance_type,
        )
        assert result == image_name

    @pytest.mark.parametrize("suffix", ["-base", "-devel"])
    def test_patch_aws_efa_image_with_registry_prefix(self, suffix: str) -> None:
        registry = "registry.example"
        image_name = (
            f"{registry}/{settings.DSTACK_BASE_IMAGE}:{settings.DSTACK_BASE_IMAGE_VERSION}{suffix}"
            f"-ubuntu{settings.DSTACK_BASE_IMAGE_UBUNTU_VERSION}"
        )
        result = self._call_resolve_provisioning_image(image_name, BackendType.AWS, "p5.48xlarge")
        expected = (
            f"{registry}/{settings.DSTACK_BASE_IMAGE}:{settings.DSTACK_BASE_IMAGE_VERSION}"
            f"-devel-efa-ubuntu{settings.DSTACK_BASE_IMAGE_UBUNTU_VERSION}"
        )
        assert result == expected
