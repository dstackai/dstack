import pytest

from dstack._internal.core.backends.azure.resources import (
    _is_valid_tag_key,
    _is_valid_tag_value,
    validate_tags,
)
from dstack._internal.core.errors import BackendError


class TestValidateTags:
    def test_valid_tags(self):
        tags = {"ValidTag": "SomeValue"}
        assert validate_tags(tags) is None

    def test_invalid_tags(self):
        tags = {"Invalid<key": "SomeValue"}
        with pytest.raises(BackendError, match="Invalid Azure resource tags"):
            validate_tags(tags)


class TestIsValidTagKey:
    @pytest.mark.parametrize(
        "key",
        [
            "ValidTagName",
            "Tag-Name_with.123",
            "🧬",
            "a" * 512,
            "Tag With Spaces",
        ],
    )
    def test_valid_tag_keys(self, key):
        assert _is_valid_tag_key(key)

    @pytest.mark.parametrize(
        "key",
        [
            "",
            "A" * 513,
            "Invalid<key>",
            "Invalid>key",
            "Invalid%key",
            "Invalid&key",
            "Invalid\\key",
            "Invalid?key",
            "Invalid/key",
        ],
    )
    def test_invalid_tag_keys(self, key):
        assert not _is_valid_tag_key(key)


class TestIsValidTagValue:
    @pytest.mark.parametrize(
        "value",
        [
            "ValidValue",
            "Value_with_special_chars!@#",
            "a" * 256,
            "",
        ],
    )
    def test_valid_tag_values(self, value):
        assert _is_valid_tag_value(value)

    @pytest.mark.parametrize(
        "value",
        [
            "a" * 257,
        ],
    )
    def test_invalid_tag_values(self, value):
        assert not _is_valid_tag_value(value)
