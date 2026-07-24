from unittest.mock import MagicMock, patch

import botocore.exceptions
import pytest

from dstack._internal.core.backends.aws.compute import AWSCompute
from dstack._internal.core.backends.aws.models import AWSAccessKeyCreds, AWSConfig
from dstack._internal.core.backends.base.compute import ComputeWithSecurityGroupSupport
from dstack._internal.core.backends.features import BACKENDS_WITH_SECURITY_GROUP_SUPPORT
from dstack._internal.core.errors import ComputeError
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import (
    InstanceAvailability,
    InstanceConfiguration,
    InstanceOfferWithAvailability,
    InstanceType,
    Resources,
    SSHKey,
)


def _config(security_group_name=None, security_group_ids=None) -> AWSConfig:
    return AWSConfig(
        creds=AWSAccessKeyCreds(access_key="test", secret_key="test"),
        regions=["us-east-1"],
        security_group_name=security_group_name,
        security_group_ids=security_group_ids,
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


def _offer(region="us-east-1") -> InstanceOfferWithAvailability:
    return InstanceOfferWithAvailability(
        backend=BackendType.AWS,
        instance=InstanceType(
            name="m5.large",
            resources=Resources(cpus=2, memory_mib=8192, gpus=[], spot=False),
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


def _run_create_instance(
    compute: AWSCompute,
    instance_config: InstanceConfiguration,
    offer: InstanceOfferWithAvailability = None,
) -> str:
    """Runs create_instance with the instances struct mocked and returns the
    security_group_id that was passed into create_instances_struct."""
    if offer is None:
        offer = _offer()
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
            instance_offer=offer,
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

    def test_uses_security_group_ids_for_region_without_managing_it(self):
        compute = _compute(_config(security_group_ids={"us-east-1": "sg-region"}))
        with patch(
            "dstack._internal.core.backends.aws.compute.aws_resources"
            ".get_security_group_id_by_name"
        ) as lookup_mock:
            security_group_id = _run_create_instance(compute, _instance_config())
        assert security_group_id == "sg-region"
        # The per-region ID is used directly: no auto-create, no name lookup.
        compute._create_security_group.assert_not_called()
        lookup_mock.assert_not_called()

    def test_security_group_ids_missing_region_falls_back_to_auto_create(self):
        compute = _compute(_config(security_group_ids={"eu-west-1": "sg-eu"}))
        # Offer region us-east-1 is not in the mapping -> fall back to auto-create.
        security_group_id = _run_create_instance(compute, _instance_config())
        compute._create_security_group.assert_called_once()
        assert security_group_id == "sg-auto"

    def test_security_group_ids_missing_region_falls_back_to_name(self):
        compute = _compute(
            _config(
                security_group_name="my-sg",
                security_group_ids={"eu-west-1": "sg-eu"},
            )
        )
        with patch(
            "dstack._internal.core.backends.aws.compute.aws_resources"
            ".get_security_group_id_by_name",
            return_value="sg-by-name",
        ) as lookup_mock:
            security_group_id = _run_create_instance(compute, _instance_config())
        # Region not in the ID map -> fall back to name lookup, not auto-create.
        assert security_group_id == "sg-by-name"
        compute._create_security_group.assert_not_called()
        lookup_mock.assert_called_once()
        assert lookup_mock.call_args.kwargs["name"] == "my-sg"
        assert lookup_mock.call_args.kwargs["vpc_id"] == "vpc-1"

    def test_security_group_name_triggers_lookup_and_uses_result(self):
        compute = _compute(_config(security_group_name="my-sg"))
        with patch(
            "dstack._internal.core.backends.aws.compute.aws_resources"
            ".get_security_group_id_by_name",
            return_value="sg-by-name",
        ) as lookup_mock:
            security_group_id = _run_create_instance(compute, _instance_config())
        assert security_group_id == "sg-by-name"
        compute._create_security_group.assert_not_called()
        lookup_mock.assert_called_once()

    def test_security_group_name_not_found_raises(self):
        compute = _compute(_config(security_group_name="missing-sg"))
        with patch(
            "dstack._internal.core.backends.aws.compute.aws_resources"
            ".get_security_group_id_by_name",
            return_value=None,
        ):
            with pytest.raises(ComputeError, match="missing-sg"):
                _run_create_instance(compute, _instance_config())
        # No silent fall-through to auto-create.
        compute._create_security_group.assert_not_called()

    def test_run_level_security_group_overrides_ids(self):
        compute = _compute(_config(security_group_ids={"us-east-1": "sg-region"}))
        security_group_id = _run_create_instance(
            compute, _instance_config(security_group="sg-run")
        )
        compute._create_security_group.assert_not_called()
        assert security_group_id == "sg-run"

    def test_run_level_security_group_overrides_name(self):
        compute = _compute(_config(security_group_name="my-sg"))
        with patch(
            "dstack._internal.core.backends.aws.compute.aws_resources"
            ".get_security_group_id_by_name"
        ) as lookup_mock:
            security_group_id = _run_create_instance(
                compute, _instance_config(security_group="sg-run")
            )
        assert security_group_id == "sg-run"
        compute._create_security_group.assert_not_called()
        lookup_mock.assert_not_called()

    def test_invalid_security_group_raises_compute_error(self):
        # A security group in the wrong VPC/region is a misconfiguration, not a
        # capacity issue: surface a clear ComputeError instead of retrying AZs.
        compute = _compute(_config(security_group_ids={"us-east-1": "sg-wrong-vpc"}))
        error = botocore.exceptions.ClientError(
            error_response={
                "Error": {
                    "Code": "InvalidGroup.NotFound",
                    "Message": "The security group 'sg-wrong-vpc' does not exist",
                }
            },
            operation_name="RunInstances",
        )
        with patch(
            "dstack._internal.core.backends.aws.compute.aws_resources.create_instances_struct",
            return_value={},
        ):
            ec2_resource = compute.session.resource.return_value
            ec2_resource.create_instances.side_effect = error
            with pytest.raises(ComputeError, match="Security group not found"):
                compute.create_instance(
                    instance_offer=_offer(),
                    instance_config=_instance_config(),
                    placement_group=None,
                )
