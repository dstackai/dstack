import pytest

from dstack._internal.core.backends.gcp import resources as gcp_resources
from dstack._internal.core.errors import BackendError


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
