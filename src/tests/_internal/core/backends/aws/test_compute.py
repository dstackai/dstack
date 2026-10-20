import json
from datetime import datetime, timezone
from typing import Iterator
from unittest.mock import Mock

import boto3
import pytest
from botocore.stub import Stubber

from dstack._internal.core.backends.aws.compute import (
    AWSCompute,
    _allocate_and_associate_eip,
)
from dstack._internal.core.backends.aws.models import AWSAccessKeyCreds, AWSConfig
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.backends.orphans import ListedResourceGroup, OwnerType

REGION = "us-east-1"
PROVIDER_REF = "abc123def456"
LAUNCH_TIME = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
PROVIDER_REF_FILTER = {"Name": "tag-key", "Values": ["dstack_provider_ref"]}


@pytest.fixture
def ec2_client() -> Iterator[Stubber]:
    client = boto3.client(
        "ec2",
        region_name=REGION,
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )
    with Stubber(client) as stubber:
        yield stubber
        stubber.assert_no_pending_responses()


@pytest.fixture
def compute(ec2_client: Stubber) -> AWSCompute:
    compute = AWSCompute(
        AWSConfig(
            creds=AWSAccessKeyCreds(access_key="test", secret_key="test"),
            regions=[REGION],
        )
    )
    compute.session = Mock()
    compute.session.client.return_value = ec2_client.client
    return compute


def _get_instance(instance_id: str, provider_ref: str = PROVIDER_REF) -> dict:
    return {
        "InstanceId": instance_id,
        "InstanceType": "p5.48xlarge",
        "LaunchTime": LAUNCH_TIME,
        "State": {"Code": 16, "Name": "running"},
        "Tags": [
            {"Key": "owner", "Value": "dstack"},
            {"Key": "dstack_provider_ref", "Value": provider_ref},
        ],
    }


def _get_address(allocation_id: str, instance_id: str) -> dict:
    return {
        "AllocationId": allocation_id,
        "PublicIp": "203.0.113.10",
        "Tags": [
            {"Key": "dstack_instance", "Value": instance_id},
            {"Key": "dstack_provider_ref", "Value": PROVIDER_REF},
        ],
    }


def _add_list_responses(ec2_client: Stubber, instances: list[dict], addresses: list[dict]):
    ec2_client.add_response(
        "describe_instances",
        {"Reservations": [{"Instances": instances}]},
        {
            "Filters": [
                PROVIDER_REF_FILTER,
                {
                    "Name": "instance-state-name",
                    "Values": ["pending", "running", "shutting-down", "stopping", "stopped"],
                },
            ]
        },
    )
    ec2_client.add_response(
        "describe_addresses",
        {"Addresses": addresses},
        {"Filters": [PROVIDER_REF_FILTER]},
    )


class TestListResourceGroups:
    def test_groups_elastic_ip_with_its_instance(self, compute: AWSCompute, ec2_client: Stubber):
        _add_list_responses(
            ec2_client,
            instances=[_get_instance("i-1")],
            addresses=[_get_address("eipalloc-1", "i-1")],
        )
        groups = compute.list_resource_groups()
        assert len(groups) == 1
        group = groups[0]
        assert group.backend == BackendType.AWS
        assert group.owner_type == OwnerType.INSTANCE
        assert group.provider_ref == PROVIDER_REF
        assert group.primary_id == "i-1"
        assert group.region == REGION
        assert group.created_at == LAUNCH_TIME
        assert "eipalloc-1" in group.description
        assert json.loads(group.backend_data or "") == {
            "instance_id": "i-1",
            "eip_allocation_ids": ["eipalloc-1"],
        }

    def test_lists_elastic_ip_of_gone_instance_as_separate_group(
        self, compute: AWSCompute, ec2_client: Stubber
    ):
        _add_list_responses(
            ec2_client, instances=[], addresses=[_get_address("eipalloc-1", "i-gone")]
        )
        groups = compute.list_resource_groups()
        assert len(groups) == 1
        group = groups[0]
        assert group.provider_ref == PROVIDER_REF
        assert group.primary_id is None
        assert group.created_at is None
        assert json.loads(group.backend_data or "") == {
            "instance_id": None,
            "eip_allocation_ids": ["eipalloc-1"],
        }

    def test_skips_resources_with_invalid_provider_ref(
        self, compute: AWSCompute, ec2_client: Stubber
    ):
        _add_list_responses(
            ec2_client, instances=[_get_instance("i-1", provider_ref="Invalid-Ref")], addresses=[]
        )
        assert compute.list_resource_groups() == []


class TestDeleteResourceGroup:
    def test_terminates_instance_and_releases_elastic_ip(
        self, compute: AWSCompute, ec2_client: Stubber
    ):
        group = ListedResourceGroup(
            backend=BackendType.AWS,
            owner_type=OwnerType.INSTANCE,
            provider_ref=PROVIDER_REF,
            primary_id="i-1",
            region=REGION,
            created_at=LAUNCH_TIME,
            description="instance i-1",
            backend_data=json.dumps({"instance_id": "i-1", "eip_allocation_ids": ["eipalloc-1"]}),
        )
        ec2_client.add_response(
            "terminate_instances", {"TerminatingInstances": []}, {"InstanceIds": ["i-1"]}
        )
        ec2_client.add_response(
            "describe_addresses",
            {"Addresses": [{"AllocationId": "eipalloc-1", "AssociationId": "eipassoc-1"}]},
            {"AllocationIds": ["eipalloc-1"]},
        )
        ec2_client.add_response("disassociate_address", {}, {"AssociationId": "eipassoc-1"})
        ec2_client.add_response("release_address", {}, {"AllocationId": "eipalloc-1"})
        compute.delete_resource_group(group)

    def test_tolerates_already_terminated_instance(self, compute: AWSCompute, ec2_client: Stubber):
        group = ListedResourceGroup(
            backend=BackendType.AWS,
            owner_type=OwnerType.INSTANCE,
            provider_ref=PROVIDER_REF,
            primary_id="i-1",
            region=REGION,
            created_at=LAUNCH_TIME,
            description="instance i-1",
            backend_data=json.dumps({"instance_id": "i-1", "eip_allocation_ids": []}),
        )
        ec2_client.add_client_error(
            "terminate_instances",
            service_error_code="InvalidInstanceID.NotFound",
            expected_params={"InstanceIds": ["i-1"]},
        )
        compute.delete_resource_group(group)


class TestAllocateAndAssociateEip:
    def test_tags_elastic_ip_with_provider_ref(self, ec2_client: Stubber):
        instance = Mock(
            instance_id="i-1",
            network_interfaces_attribute=[
                {"NetworkInterfaceId": "eni-1", "Attachment": {"DeviceIndex": 0}}
            ],
        )
        ec2_client.add_response(
            "allocate_address",
            {"AllocationId": "eipalloc-1", "PublicIp": "203.0.113.10"},
            {
                "Domain": "vpc",
                "TagSpecifications": [
                    {
                        "ResourceType": "elastic-ip",
                        "Tags": [
                            {"Key": "owner", "Value": "dstack"},
                            {"Key": "dstack_instance", "Value": "i-1"},
                            {"Key": "dstack_project", "Value": "main"},
                            {"Key": "dstack_provider_ref", "Value": PROVIDER_REF},
                        ],
                    }
                ],
            },
        )
        ec2_client.add_response(
            "associate_address",
            {"AssociationId": "eipassoc-1"},
            {
                "AllocationId": "eipalloc-1",
                "NetworkInterfaceId": "eni-1",
                "AllowReassociation": False,
            },
        )
        assert _allocate_and_associate_eip(
            ec2_client=ec2_client.client,
            instance=instance,
            project_name="main",
            provider_ref=PROVIDER_REF,
            backend_tags=None,
        ) == ("203.0.113.10", "eipalloc-1")
