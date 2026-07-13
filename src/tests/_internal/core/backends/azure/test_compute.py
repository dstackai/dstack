from unittest.mock import Mock, patch

import pytest

from dstack._internal import settings
from dstack._internal.core.backends.azure import utils as azure_utils
from dstack._internal.core.backends.azure.compute import AzureCompute, VMImageVariant
from dstack._internal.core.backends.azure.models import AzureClientCreds, AzureConfig
from dstack._internal.core.models.instances import (
    Gpu,
    InstanceAvailability,
    InstanceConfiguration,
    InstanceOfferWithAvailability,
    InstanceType,
    Resources,
    SSHKey,
)


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


def _config(network_security_group_names=None) -> AzureConfig:
    return AzureConfig(
        creds=AzureClientCreds(tenant_id="t", client_id="c", client_secret="s"),
        tenant_id="ten1",
        subscription_id="sub1",
        resource_group="my-rg",
        regions=["eastus", "westeurope"],
        network_security_group_names=network_security_group_names,
    )


def _offer(region="eastus") -> InstanceOfferWithAvailability:
    return InstanceOfferWithAvailability(
        backend="azure",
        instance=InstanceType(
            name="Standard_DS1_v2",
            resources=Resources(cpus=1, memory_mib=3500, gpus=[], spot=False),
        ),
        region=region,
        price=0.1,
        availability=InstanceAvailability.AVAILABLE,
    )


def _instance_config(security_group=None) -> InstanceConfiguration:
    return InstanceConfiguration(
        project_name="main",
        instance_name="test-instance",
        user="test-user",
        ssh_keys=[SSHKey(public="ssh-rsa test")],
        security_group=security_group,
    )


class TestAzureComputeNetworkSecurityGroup:
    @pytest.mark.parametrize(
        ["instance_sg", "nsg_names", "region", "expected"],
        [
            # No mapping, no instance security_group -> auto-derived default per location.
            [
                None,
                None,
                "eastus",
                azure_utils.get_default_network_security_group_name("my-rg", "eastus"),
            ],
            # Location present in the mapping resolves to the mapped NSG name.
            [None, {"eastus": "config-nsg"}, "eastus", "config-nsg"],
            # Location absent from the mapping falls back to the auto-derived default name.
            [
                None,
                {"eastus": "config-nsg"},
                "westeurope",
                azure_utils.get_default_network_security_group_name("my-rg", "westeurope"),
            ],
            # instance_config.security_group takes precedence when no mapping is set.
            ["instance-nsg", None, "eastus", "instance-nsg"],
            # instance_config.security_group takes precedence over the mapping.
            ["instance-nsg", {"eastus": "config-nsg"}, "eastus", "instance-nsg"],
        ],
    )
    def test_create_instance_resolves_network_security_group(
        self, instance_sg, nsg_names, region, expected
    ):
        with (
            patch("dstack._internal.core.backends.azure.compute.compute_mgmt"),
            patch("dstack._internal.core.backends.azure.compute.network_mgmt"),
            patch(
                "dstack._internal.core.backends.azure.compute"
                ".get_resource_group_network_subnet_or_error",
                return_value=("net-rg", "net", "subnet"),
            ),
            patch("dstack._internal.core.backends.azure.compute._get_image_ref"),
            patch(
                "dstack._internal.core.backends.azure.compute._create_instance_and_wait"
            ) as create_and_wait_mock,
            patch(
                "dstack._internal.core.backends.azure.compute._get_vm_public_private_ips",
                return_value=("1.2.3.4", "10.0.0.1"),
            ),
        ):
            vm_mock = Mock()
            vm_mock.name = "test-vm-id"
            create_and_wait_mock.return_value = vm_mock
            compute = AzureCompute(
                config=_config(network_security_group_names=nsg_names), credential=Mock()
            )
            compute.create_instance(
                instance_offer=_offer(region=region),
                instance_config=_instance_config(security_group=instance_sg),
                placement_group=None,
            )
            _, kwargs = create_and_wait_mock.call_args
            assert kwargs["network_security_group"] == expected
