import google.cloud.compute_v1 as compute_v1
import pytest

from dstack._internal.core.backends.gcp import resources as gcp_resources
from dstack._internal.core.errors import BackendError, ComputeError


def _usable_subnet(
    project: str, vpc: str, region: str, subnet: str
) -> compute_v1.UsableSubnetwork:
    return compute_v1.UsableSubnetwork(
        network=(
            f"https://www.googleapis.com/compute/v1/projects/{project}/global/networks/{vpc}"
        ),
        subnetwork=(
            f"https://www.googleapis.com/compute/v1/projects/{project}"
            f"/regions/{region}/subnetworks/{subnet}"
        ),
    )


class TestGetVpcSubnetOrError:
    def test_returns_first_subnet_when_name_not_specified(self):
        usable_subnets = [
            _usable_subnet("proj", "my-vpc", "us-west1", "subnet-a"),
            _usable_subnet("proj", "my-vpc", "us-west1", "subnet-b"),
        ]
        subnet = gcp_resources.get_vpc_subnet_or_error(
            vpc_name="my-vpc",
            region="us-west1",
            usable_subnets=usable_subnets,
        )
        assert subnet == "projects/proj/regions/us-west1/subnetworks/subnet-a"

    def test_returns_subnet_matching_specified_name(self):
        usable_subnets = [
            _usable_subnet("proj", "my-vpc", "us-west1", "subnet-a"),
            _usable_subnet("proj", "my-vpc", "us-west1", "subnet-b"),
        ]
        subnet = gcp_resources.get_vpc_subnet_or_error(
            vpc_name="my-vpc",
            region="us-west1",
            usable_subnets=usable_subnets,
            subnetwork_name="subnet-b",
        )
        assert subnet == "projects/proj/regions/us-west1/subnetworks/subnet-b"

    def test_raises_when_specified_subnet_not_found(self):
        usable_subnets = [
            _usable_subnet("proj", "my-vpc", "us-west1", "subnet-a"),
        ]
        with pytest.raises(ComputeError, match=r"Available subnetworks: \['subnet-a'\]"):
            gcp_resources.get_vpc_subnet_or_error(
                vpc_name="my-vpc",
                region="us-west1",
                usable_subnets=usable_subnets,
                subnetwork_name="missing",
            )

    def test_raises_when_specified_subnet_in_another_region(self):
        usable_subnets = [
            _usable_subnet("proj", "my-vpc", "us-west1", "subnet-a"),
            _usable_subnet("proj", "my-vpc", "europe-west4", "subnet-b"),
        ]
        with pytest.raises(ComputeError, match="VPC my-vpc in region us-west1"):
            gcp_resources.get_vpc_subnet_or_error(
                vpc_name="my-vpc",
                region="us-west1",
                usable_subnets=usable_subnets,
                subnetwork_name="subnet-b",
            )

    def test_matches_subnet_by_short_name_in_shared_vpc(self):
        usable_subnets = [
            _usable_subnet("host-proj", "shared-vpc", "us-west1", "subnet-a"),
            _usable_subnet("host-proj", "shared-vpc", "us-west1", "subnet-b"),
        ]
        subnet = gcp_resources.get_vpc_subnet_or_error(
            vpc_name="shared-vpc",
            region="us-west1",
            usable_subnets=usable_subnets,
            subnetwork_name="subnet-b",
        )
        assert subnet == "projects/host-proj/regions/us-west1/subnetworks/subnet-b"


class TestValidateLabels:
    def test_validate_valid_labels(self):
        labels = {
            "env": "production",
            "project": "gcp-label-validator",
        }
        assert gcp_resources.validate_labels(labels) is None

    def test_validate_invalid_labels(self):
        labels = {
            "InvalidName": "validvalue",
            "valid-name": "invalid_value!",
        }
        with pytest.raises(BackendError, match="Invalid resource label"):
            gcp_resources.validate_labels(labels)


class TestIsValidResourceName:
    @pytest.mark.parametrize(
        "name",
        [
            "",
            "1",
            "a" * 64,
            "-startswithdash",
            "1startswithdigit",
            "Uppercase",
        ],
    )
    def test_invalid_name(self, name):
        assert not gcp_resources.is_valid_resource_name(name)

    @pytest.mark.parametrize("name", ["a", "some-name-with-dashes-123", "asd_asd"])
    def test_valid_name(self, name):
        assert gcp_resources.is_valid_resource_name(name)


class TestIsValidLabelValue:
    @pytest.mark.parametrize(
        "name",
        [
            "a" * 64,
            "Uppercase",
        ],
    )
    def test_invalid_label_value(self, name):
        assert not gcp_resources.is_valid_label_value(name)

    @pytest.mark.parametrize("name", ["", "a", "---", "some-lable-with-dashes-123"])
    def test_valid_label_value(self, name):
        assert gcp_resources.is_valid_label_value(name)
