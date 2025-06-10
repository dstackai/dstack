import logging
from unittest.mock import Mock

import pytest

from dstack._internal.core.backends.aws.models import AWSOSImage, AWSOSImageConfig
from dstack._internal.core.backends.aws.resources import (
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
            cuda=False,
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
        monkeypatch.setattr("dstack.version.base_image", "0.0")
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
                cuda=False,
                instance_type="some",
            )
        assert "image 'dstack-0.0' not found" in caplog.text

    @pytest.mark.parametrize(
        ["cuda", "expected"],
        [
            [False, "dstack-0.0"],
            [True, "dstack-cuda-0.0"],
        ],
    )
    def test_uses_dstack_image_name_and_account_id_if_image_config_not_provided(
        self, monkeypatch: pytest.MonkeyPatch, ec2_client_mock: Mock, cuda: bool, expected: str
    ):
        monkeypatch.setattr("dstack.version.base_image", "0.0")
        _, username = get_image_id_and_username(
            ec2_client_mock,
            cuda=cuda,
            instance_type="some",
        )
        assert username == "ubuntu"
        ec2_client_mock.describe_images.assert_called_once_with(
            Filters=[{"Name": "name", "Values": [expected]}], Owners=["142421590066"]
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
            cuda=cuda,
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
                cuda=False,
                instance_type="some",
                image_config=image_config,
            )
        assert "cpu image not configured" in caplog.text
