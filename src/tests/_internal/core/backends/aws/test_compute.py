from unittest.mock import MagicMock, patch

import pytest

from dstack._internal.core.backends.aws.compute import AWSCompute
from dstack._internal.core.backends.aws.models import AWSAccessKeyCreds, AWSConfig
from dstack._internal.core.backends.base.compute import ComputeWithSecurityGroupSupport
from dstack._internal.core.backends.features import BACKENDS_WITH_SECURITY_GROUP_SUPPORT
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import (
    InstanceAvailability,
    InstanceConfiguration,
    InstanceOfferWithAvailability,
    InstanceType,
    Resources,
    SSHKey,
)


def _config(security_group_id=None) -> AWSConfig:
    return AWSConfig(
        creds=AWSAccessKeyCreds(access_key="test", secret_key="test"),
        regions=["us-east-1"],
        security_group_id=security_group_id,
    )


def _compute(config: AWSConfig) -> AWSCompute:
    compute = AWSCompute(config)
    compute.session = MagicMock()
    # Bypass everything that would hit AWS before/after the security group resolution.
    compute._get_maximum_efa_interfaces = MagicMock(return_value=0)
    compute._get_vpc_id_subnets_ids_or_error = MagicMock(return_value=("vpc-1", ["subnet-1"]))
    compute._get_subnets_availability_zones = MagicMock(return_value={"subnet-1": "az-1"})
    compute._get_image_id_and_username = MagicMock(return_value=("ami-1", "ubuntu"))
    compute._create_security_group = MagicMock(return_value="sg-auto")
    return compute


def _offer() -> InstanceOfferWithAvailability:
    return InstanceOfferWithAvailability(
        backend=BackendType.AWS,
        instance=InstanceType(
            name="m5.large",
            resources=Resources(cpus=2, memory_mib=8192, gpus=[], spot=False),
        ),
        region="us-east-1",
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


def _run_create_instance(compute: AWSCompute, instance_config: InstanceConfiguration) -> str:
    """Runs create_instance with the instances struct mocked and returns the
    security_group_id that was passed into create_instances_struct."""
    with patch(
        "dstack._internal.core.backends.aws.compute.aws_resources.create_instances_struct"
    ) as struct_mock:
        struct_mock.return_value = {}
        ec2_resource = compute.session.resource.return_value
        instance_mock = MagicMock()
        instance_mock.instance_id = "i-123"
        instance_mock.capacity_reservation_id = None
        ec2_resource.create_instances.return_value = [instance_mock]
        compute.create_instance(
            instance_offer=_offer(),
            instance_config=instance_config,
            placement_group=None,
        )
        assert struct_mock.call_count == 1
        return struct_mock.call_args.kwargs["security_group_id"]


class TestAWSComputeSecurityGroupSupport:
    def test_registered_as_security_group_backend(self):
        assert issubclass(AWSCompute, ComputeWithSecurityGroupSupport)
        assert BackendType.AWS in BACKENDS_WITH_SECURITY_GROUP_SUPPORT

    def test_auto_creates_group_when_no_custom_sg_configured(self):
        compute = _compute(_config())
        security_group_id = _run_create_instance(compute, _instance_config())
        # dstack's auto-create-and-manage path is used.
        compute._create_security_group.assert_called_once()
        assert security_group_id == "sg-auto"

    def test_uses_project_level_security_group_id_without_managing_it(self):
        compute = _compute(_config(security_group_id="sg-project"))
        security_group_id = _run_create_instance(compute, _instance_config())
        # No auto-create / rule-management happens for a custom SG.
        compute._create_security_group.assert_not_called()
        assert security_group_id == "sg-project"

    def test_run_level_security_group_overrides_project_level(self):
        compute = _compute(_config(security_group_id="sg-project"))
        security_group_id = _run_create_instance(
            compute, _instance_config(security_group="sg-run")
        )
        compute._create_security_group.assert_not_called()
        assert security_group_id == "sg-run"

    @pytest.mark.parametrize(
        ["config_sg", "instance_sg", "expected"],
        [
            [None, None, "sg-auto"],
            ["sg-project", None, "sg-project"],
            [None, "sg-run", "sg-run"],
            ["sg-project", "sg-run", "sg-run"],
        ],
    )
    def test_precedence(self, config_sg, instance_sg, expected):
        compute = _compute(_config(security_group_id=config_sg))
        security_group_id = _run_create_instance(compute, _instance_config(instance_sg))
        assert security_group_id == expected
