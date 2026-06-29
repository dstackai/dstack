import pytest
from pydantic import BaseModel

from dstack._internal.core.models.common import CoreModel
from dstack._internal.core.services.diff import (
    ModelDiff,
    ModelFieldDiff,
    diff_models,
    flatten_diff_fields,
)


class TestDiffModels:
    class _BaseModelA(BaseModel):
        a: int
        b: str

    class _BaseModelB(BaseModel):
        c: int

    class _BaseModelAB(_BaseModelA, _BaseModelB):
        pass

    class _CoreModelA(CoreModel):
        a: int
        b: str

    class _CoreModelB(CoreModel):
        c: int

    class _CoreModelAB(_CoreModelA, _CoreModelB):
        pass

    @pytest.mark.parametrize(
        ("old", "new", "expected"),
        [
            pytest.param(
                _BaseModelA(a=1, b="x"),
                _BaseModelA(a=1, b="y"),
                {"b": ModelFieldDiff(old="x", new="y")},
                id="base-model",
            ),
            pytest.param(
                _CoreModelA(a=1, b="x"),
                _CoreModelA(a=1, b="y"),
                {"b": ModelFieldDiff(old="x", new="y")},
                id="core-model",
            ),
            pytest.param(
                _BaseModelA(a=1, b="x"),
                _BaseModelA(a=1, b="x"),
                {},
                id="base-model-no-diff",
            ),
            pytest.param(
                _CoreModelA(a=1, b="x"),
                _CoreModelA(a=1, b="x"),
                {},
                id="core-model-no-diff",
            ),
            pytest.param(
                _CoreModelA.__request__(a=1, b="x"),
                _CoreModelA.__request__(a=1, b="y"),
                {"b": ModelFieldDiff(old="x", new="y")},
                id="core-model-request",
            ),
            pytest.param(
                _CoreModelA.__response__(a=1, b="x"),
                _CoreModelA.__response__(a=1, b="y"),
                {"b": ModelFieldDiff(old="x", new="y")},
                id="core-model-response",
            ),
            pytest.param(
                _CoreModelA.__request__(a=1, b="x"),
                _CoreModelA.__response__(a=1, b="y"),
                {"b": ModelFieldDiff(old="x", new="y")},
                id="core-model-request-response",
            ),
            pytest.param(
                _CoreModelA(a=1, b="x"),
                _CoreModelA.__response__(a=1, b="y"),
                {"b": ModelFieldDiff(old="x", new="y")},
                id="core-model-base-request",
            ),
            pytest.param(
                _CoreModelA(a=1, b="x"),
                _CoreModelA.__response__(a=1, b="y"),
                {"b": ModelFieldDiff(old="x", new="y")},
                id="core-model-base-response",
            ),
        ],
    )
    def test_diff_models(self, old: BaseModel, new: BaseModel, expected: ModelDiff) -> None:
        assert diff_models(old, new) == expected

    @pytest.mark.parametrize(
        ("old", "new"),
        [
            pytest.param(
                _BaseModelA(a=1, b="x"),
                _BaseModelB(c=2),
                id="different-base-models",
            ),
            pytest.param(
                _BaseModelA(a=1, b="x"),
                _BaseModelAB(a=1, b="x", c=2),
                id="base-model-and-subclass",
            ),
            pytest.param(
                _CoreModelA(a=1, b="x"),
                _CoreModelB(c=2),
                id="different-core-models",
            ),
            pytest.param(
                _CoreModelA(a=1, b="x"),
                _CoreModelAB(a=1, b="x", c=2),
                id="core-model-and-subclass",
            ),
        ],
    )
    def test_type_mismatch(self, old: BaseModel, new: BaseModel) -> None:
        with pytest.raises(
            TypeError, match="Both instances must be of the same Pydantic model class."
        ):
            diff_models(old, new)


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
