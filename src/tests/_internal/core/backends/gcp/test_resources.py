import pytest

from dstack._internal.core.backends.gcp import resources as gcp_resources


class TestIsValidResourceName:
    @pytest.mark.parametrize(
        "name",
        [
            "",
            "1",
            "a" * 64,
            "-startswithdash",
            "1startswithdigit",
            "asd_asd",
            "Uppercase",
        ],
    )
    def test_invalid_name(self, name):
        assert not gcp_resources.is_valid_resource_name(name)

    @pytest.mark.parametrize("name", ["a", "some-name-with-dashes-123"])
    def test_valid_name(self, name):
        assert gcp_resources.is_valid_resource_name(name)


class TestIsValidLabelValue:
    @pytest.mark.parametrize(
        "name",
        [
            "a" * 64,
            "asd_asd",
            "Uppercase",
        ],
    )
    def test_invalid_label_value(self, name):
        assert not gcp_resources.is_valid_label_value(name)

    @pytest.mark.parametrize("name", ["", "a", "---", "some-lable-with-dashes-123"])
    def test_valid_label_value(self, name):
        assert gcp_resources.is_valid_label_value(name)
