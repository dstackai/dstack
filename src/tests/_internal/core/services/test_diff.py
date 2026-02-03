import pytest

from dstack._internal.core.services.diff import ModelDiff, ModelFieldDiff, flatten_diff_fields


@pytest.mark.parametrize(
    "diff,expected",
    [
        pytest.param({}, [], id="empty_diff"),
        pytest.param(
            {
                "field1": ModelFieldDiff(old="old1", new="new1"),
                "field2": ModelFieldDiff(old="old2", new="new2"),
            },
            ["field1", "field2"],
            id="multiple_fields",
        ),
        pytest.param(
            {
                "field1": ModelFieldDiff(old="old1", new="new1"),
                "nested": {
                    "sub1": ModelFieldDiff(old="old_sub1", new="new_sub1"),
                },
            },
            ["field1", "nested.sub1"],
            id="nested_single_level",
        ),
        pytest.param(
            {
                "field1": ModelFieldDiff(old="old1", new="new1"),
                "level1": {
                    "level2": {
                        "level3": {"deep_field": ModelFieldDiff(old="deep_old", new="deep_new")},
                        "field2": ModelFieldDiff(old="old2", new="new2"),
                    },
                    "field3": ModelFieldDiff(old="old3", new="new3"),
                },
            },
            ["field1", "level1.level2.level3.deep_field", "level1.level2.field2", "level1.field3"],
            id="nested_multiple_levels",
        ),
        pytest.param(
            {
                "field1": ModelFieldDiff(old="old1", new="new1"),
                "empty_nested": {},
                "nested_with_empty": {
                    "empty_sub": {},
                    "field2": ModelFieldDiff(old="old2", new="new2"),
                },
            },
            ["field1", "nested_with_empty.field2"],
            id="empty_nested",
        ),
    ],
)
def test_flatten_diff_fields(diff: ModelDiff, expected: list[str]):
    """Test flatten_diff_fields with various diff structures."""
    result = flatten_diff_fields(diff)
    assert result == expected
