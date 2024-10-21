import pytest

from dstack._internal.core.backends.aws.resources import (
    _is_valid_tag_key,
    _is_valid_tag_value,
    validate_tags,
)
from dstack._internal.core.errors import ComputeError


class TestIsValidTagKey:
    @pytest.mark.parametrize(
        "key",
        [
            "Environment",
            "Project123",
            "special-chars-+/@=:",
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
        with pytest.raises(ComputeError, match="Invalid resource tags"):
            validate_tags(tags)
