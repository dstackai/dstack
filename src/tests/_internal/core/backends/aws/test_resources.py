import logging
from unittest.mock import Mock

import pytest

from dstack._internal.core.backends.aws.models import AWSOSImage, AWSOSImageConfig
from dstack._internal.core.backends.aws.resources import (
    _create_network_interfaces_struct,
    _is_valid_tag_key,
    _is_valid_tag_value,
    get_image_id_and_username,
    validate_tags,
)
from dstack._internal.core.errors import BackendError, ComputeResourceNotFoundError


class TestIsValidTagKey:
    @pytest.mark.parametrize(
        "key",
        [
            "Environment",
            "Project123",
            "special-chars-+/@=:_",
            "a" * 128,
        ],
    )
    def test_valid_tag_key(self, key):
        assert _is_valid_tag_key(key)

    @pytest.mark.parametrize(
        "key",
        [
            "aws:reserved",
            "key\twith\nweird\nspaces",
            "",
            "a" * 129,
            "Invalid#Char",
        ],
    )
    def test_invalid_tag_key(self, key):
        assert not _is_valid_tag_key(key)


class TestIsValidTagValue:
    @pytest.mark.parametrize(
        "value",
        [
            "Production",
            "v1.0",
            "",
            "a" * 256,
        ],
    )
    def test_valid_tag_value(self, value):
        assert _is_valid_tag_value(value) is True

    @pytest.mark.parametrize(
        "value",
        [
            "a" * 257,
            "Invalid#Value",
        ],
    )
    def test_invalid_tag_value(self, value):
        assert _is_valid_tag_value(value) is False


class TestValidateTags:
    def test_validate_valid_tags(self):
        tags = {
            "Environment": "Production",
            "Project": "AWS_Tag_Validator",
        }
        assert validate_tags(tags) is None

    def test_validate_invalid_tags(self):
        tags = {"aws:ReservedKey": "SomeValue", "ValidKey": "Invalid#Value"}
        with pytest.raises(BackendError, match="Invalid resource tags"):
            validate_tags(tags)


class TestGetImageIdAndUsername:
    @pytest.fixture
    def ec2_client_mock(self) -> Mock:
        mock = Mock(spec_set=["describe_images"])
        mock.describe_images.return_value = {
            "Images": [
                {
                    "ImageId": "ami-00000000000000000",
                    "State": "available",
                    "CreationDate": "2000-01-01T00:00:00.000Z",
                },
            ],
        }
        return mock

    def test_returns_the_latest_available(self, ec2_client_mock: Mock):
        ec2_client_mock.describe_images.return_value = {
            "Images": [
                # the latest, but not available
                {
                    "ImageId": "ami-00000000000000001",
                    "State": "failed",
                    "CreationDate": "2024-01-01T00:00:00.000Z",
                },
                # available, but not the latest
                {
                    "ImageId": "ami-00000000000000002",
                    "State": "available",
                    "CreationDate": "2022-01-01T00:00:00.000Z",
                },
                # the latest available
                {
                    "ImageId": "ami-00000000000000003",
                    "State": "available",
                    "CreationDate": "2023-01-01T00:00:00.000Z",
                },
            ]
        }
        image_id, username = get_image_id_and_username(
            ec2_client_mock,
            gpu_name=None,
            instance_type="some",
        )
        assert image_id == "ami-00000000000000003"
        assert username == "ubuntu"

    def test_raises_resource_not_found_if_none_available(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
        ec2_client_mock: Mock,
    ):
        monkeypatch.setattr("dstack._internal.settings.DSTACK_VM_BASE_IMAGE_VERSION", "0.0")
        caplog.set_level(logging.WARNING)
        ec2_client_mock.describe_images.return_value = {
            "Images": [
                {
                    "ImageId": "ami-00000000000000000",
                    "State": "failed",
                    "CreationDate": "2000-01-01T00:00:00.000Z",
                },
            ]
        }
        with pytest.raises(ComputeResourceNotFoundError):
            get_image_id_and_username(
                ec2_client_mock,
                gpu_name=None,
                instance_type="some",
            )
        assert "image 'dstack-0.0' not found" in caplog.text

    @pytest.mark.parametrize(
        ["cuda", "expected_name", "expected_owner"],
        [
            [False, "dstack-0.0", "142421590066"],
            [
                True,
                "Deep Learning Base OSS Nvidia Driver GPU AMI (Ubuntu 22.04) *",
                "898082745236",
            ],
        ],
    )
    def test_uses_default_image_name_and_account_id_if_image_config_not_provided(
        self,
        monkeypatch: pytest.MonkeyPatch,
        ec2_client_mock: Mock,
        cuda: bool,
        expected_name: str,
        expected_owner: str,
    ):
        monkeypatch.setattr("dstack._internal.settings.DSTACK_VM_BASE_IMAGE_VERSION", "0.0")
        _, username = get_image_id_and_username(
            ec2_client_mock,
            gpu_name="A10G" if cuda else None,
            instance_type="some",
        )
        assert username == "ubuntu"
        ec2_client_mock.describe_images.assert_called_once_with(
            Filters=[{"Name": "name", "Values": [expected_name]}], Owners=[expected_owner]
        )

    @pytest.mark.parametrize(
        ["cuda", "expected_name", "expected_owner", "expected_username"],
        [
            [False, "cpu-ami", "123456789012", "debian"],
            [True, "nvidia-ami", "self", "dstack"],
        ],
    )
    def test_uses_image_config_if_provided(
        self,
        ec2_client_mock: Mock,
        cuda: bool,
        expected_name: str,
        expected_owner: str,
        expected_username: str,
    ):
        image_config = AWSOSImageConfig(
            cpu=AWSOSImage(
                name="cpu-ami",
                owner="123456789012",
                user="debian",
            ),
            nvidia=AWSOSImage(
                name="nvidia-ami",
                user="dstack",
            ),
        )
        _, username = get_image_id_and_username(
            ec2_client_mock,
            gpu_name="A10G" if cuda else None,
            instance_type="some",
            image_config=image_config,
        )
        assert username == expected_username
        ec2_client_mock.describe_images.assert_called_once_with(
            Filters=[{"Name": "name", "Values": [expected_name]}],
            Owners=[expected_owner],
        )

    def test_raises_resource_not_found_if_image_config_property_not_set(
        self, caplog: pytest.LogCaptureFixture, ec2_client_mock: Mock
    ):
        caplog.set_level(logging.WARNING)
        image_config = AWSOSImageConfig(
            nvidia=AWSOSImage(
                name="nvidia-ami",
                user="dstack",
            ),
        )
        with pytest.raises(ComputeResourceNotFoundError):
            get_image_id_and_username(
                ec2_client_mock,
                gpu_name=None,
                instance_type="some",
                image_config=image_config,
            )
        assert "cpu image not configured" in caplog.text


class TestCreateNetworkInterfacesStruct:
    def test_non_efa_instance_single_interface(self):
        interfaces = _create_network_interfaces_struct(
            instance_type="m5.large",
            subnet_id="subnet-1",
            security_group_id="sg-1",
            allocate_public_ip=True,
            max_efa_interfaces=0,
        )
        assert interfaces == [
            {
                "AssociatePublicIpAddress": True,
                "DeviceIndex": 0,
                "SubnetId": "subnet-1",
                "Groups": ["sg-1"],
                "InterfaceType": "interface",
            },
        ]

    def test_non_efa_instance_no_public_ip(self):
        interfaces = _create_network_interfaces_struct(
            instance_type="m5.large",
            subnet_id="subnet-1",
            security_group_id="sg-1",
            allocate_public_ip=False,
            max_efa_interfaces=0,
        )
        assert interfaces[0]["AssociatePublicIpAddress"] is False
        assert interfaces[0]["InterfaceType"] == "interface"

    def test_single_efa_interface(self):
        interfaces = _create_network_interfaces_struct(
            instance_type="g5.8xlarge",
            subnet_id="subnet-1",
            security_group_id="sg-1",
            allocate_public_ip=True,
            max_efa_interfaces=1,
        )
        # multi_eni is False, so the single EFA NIC keeps the public IP
        assert interfaces == [
            {
                "AssociatePublicIpAddress": True,
                "DeviceIndex": 0,
                "SubnetId": "subnet-1",
                "Groups": ["sg-1"],
                "InterfaceType": "efa",
            },
        ]

    def test_multi_efa_instance(self):
        interfaces = _create_network_interfaces_struct(
            instance_type="p4d.24xlarge",
            subnet_id="subnet-1",
            security_group_id="sg-1",
            allocate_public_ip=True,
            max_efa_interfaces=4,
        )
        # Multiple NICs disable auto-assigned public IP on every interface
        assert interfaces[0] == {
            "AssociatePublicIpAddress": False,
            "DeviceIndex": 0,
            "SubnetId": "subnet-1",
            "Groups": ["sg-1"],
            "InterfaceType": "efa",
        }
        assert interfaces[1:] == [
            {
                "AssociatePublicIpAddress": False,
                "NetworkCardIndex": i,
                "DeviceIndex": 1,
                "SubnetId": "subnet-1",
                "Groups": ["sg-1"],
                "InterfaceType": "efa-only",
            }
            for i in range(1, 4)
        ]

    def test_p5_uses_efa_every_fourth_interface(self):
        interfaces = _create_network_interfaces_struct(
            instance_type="p5.48xlarge",
            subnet_id="subnet-1",
            security_group_id="sg-1",
            allocate_public_ip=True,
            max_efa_interfaces=32,
        )
        assert len(interfaces) == 32
        assert all(i["NetworkCardIndex"] == idx for idx, i in enumerate(interfaces) if idx > 0)
        # The primary NIC is a combined efa interface
        assert interfaces[0]["InterfaceType"] == "efa"
        assert "NetworkCardIndex" not in interfaces[0]
        # Every 4th secondary NIC is a combined efa interface, the rest are efa-only
        for idx, interface in enumerate(interfaces[1:], start=1):
            expected = "efa" if idx % 4 == 0 else "efa-only"
            assert interface["InterfaceType"] == expected, idx

    def test_p6_b200_efa_on_every_card(self):
        # p6-b200 has 8 EFA-capable network cards (indexes 0-7), handled by the generic path
        interfaces = _create_network_interfaces_struct(
            instance_type="p6-b200.48xlarge",
            subnet_id="subnet-1",
            security_group_id="sg-1",
            allocate_public_ip=True,
            max_efa_interfaces=8,
        )
        assert len(interfaces) == 8
        assert interfaces[0] == {
            "AssociatePublicIpAddress": False,
            "DeviceIndex": 0,
            "SubnetId": "subnet-1",
            "Groups": ["sg-1"],
            "InterfaceType": "efa",
        }
        assert interfaces[1:] == [
            {
                "AssociatePublicIpAddress": False,
                "NetworkCardIndex": i,
                "DeviceIndex": 1,
                "SubnetId": "subnet-1",
                "Groups": ["sg-1"],
                "InterfaceType": "efa-only",
            }
            for i in range(1, 8)
        ]

    def test_p6_b300_ena_only_primary_nic(self):
        # p6-b300 has 17 network cards: the primary (index 0) supports only ENA, the remaining
        # 16 cards (indexes 1-16) support EFA. max_efa_interfaces is 16.
        interfaces = _create_network_interfaces_struct(
            instance_type="p6-b300.48xlarge",
            subnet_id="subnet-1",
            security_group_id="sg-1",
            allocate_public_ip=True,
            max_efa_interfaces=16,
        )
        # 1 ENA primary + 16 EFA secondary cards
        assert len(interfaces) == 17
        # Primary card is a plain ENA interface, not EFA
        assert interfaces[0] == {
            "AssociatePublicIpAddress": False,
            "DeviceIndex": 0,
            "SubnetId": "subnet-1",
            "Groups": ["sg-1"],
            "InterfaceType": "interface",
        }
        # EFA-only interfaces span network card indexes 1-16
        assert interfaces[1:] == [
            {
                "AssociatePublicIpAddress": False,
                "NetworkCardIndex": i,
                "DeviceIndex": 1,
                "SubnetId": "subnet-1",
                "Groups": ["sg-1"],
                "InterfaceType": "efa-only",
            }
            for i in range(1, 17)
        ]
