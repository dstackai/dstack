import pytest

from dstack._internal.utils.tags import is_valid_tag_key, is_valid_tag_value, validate_tags


class TestIsValidTagKey:
    @pytest.mark.parametrize(
        "key",
        [
            "Environment",
            "Project123",
            "special-chars_",
            "a" * 60,
        ],
    )
    def test_valid_tag_key(self, key):
        assert is_valid_tag_key(key)

    @pytest.mark.parametrize(
        "key",
        [
            "key\twith\nweird\nspaces",
            "",
            "a" * 61,
            "Invalid#Char",
        ],
    )
    def test_invalid_tag_key(self, key):
        assert not is_valid_tag_key(key)


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
        assert is_valid_tag_value(value) is True

    @pytest.mark.parametrize(
        "value",
        [
            "a" * 257,
            "Invalid#Value",
        ],
    )
    def test_invalid_tag_value(self, value):
        assert is_valid_tag_value(value) is False


class TestValidateTags:
    def test_validate_valid_tags(self):
        tags = {
            "Environment": "Production",
            "project": "Tag_Validator",
        }
        assert validate_tags(tags) is None

    @pytest.mark.parametrize(
        "tags",
        [
            {"invalidkey!": "SomeValue"},
            {"ValidKey": "Invalid#Value"},
        ],
    )
    def test_validate_invalid_tags(self, tags):
        with pytest.raises(ValueError):
            validate_tags(tags)
