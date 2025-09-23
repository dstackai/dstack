from argparse import Namespace

import pytest

from dstack._internal.core.backends.kubernetes.utils import get_value


class TestGetValue:
    def test_attribute_with_dot(self):
        assert get_value(Namespace(field=False), ".field", bool) is False

    def test_attribute_without_dot(self):
        assert get_value(Namespace(field=False), "field", bool) is False

    def test_index_with_dot(self):
        assert get_value([False, True], ".[1]", bool) is True

    def test_index_without_dot(self):
        assert get_value([False, True], "[1]", bool) is True

    def test_key_with_dot(self):
        assert get_value({"field": True}, ".['field']", bool) is True

    def test_key_without_dot(self):
        assert get_value({"field": True}, "['field']", bool) is True

    def test_nested(self):
        obj = Namespace(sensors=[{"speed": Namespace(values=[127, 112, 98])}])
        assert get_value(obj, ".sensors[0]['speed'].values[-1]", int) == 98

    def test_optional_is_missing(self):
        obj = Namespace(sensors=[{"speed": Namespace(values=[127, 112, 98])}])
        assert get_value(obj, ".sensors[0]['altitude'].values[-1]", int) is None

    @pytest.mark.parametrize(
        ["obj", "path", "exctype"],
        [
            pytest.param(Namespace(), ".field", AttributeError, id="attribute"),
            pytest.param([], ".[0]", IndexError, id="index"),
            pytest.param({}, ".['test']", KeyError, id="key"),
            pytest.param(Namespace(), ".['test']", TypeError, id="not-subscriptable"),
        ],
    )
    def test_required_is_missing(self, obj: object, path: str, exctype: type[Exception]):
        with pytest.raises(exctype, match="Failed to traverse"):
            get_value(obj, path, int, required=True)

    def test_required_is_null(self):
        obj = Namespace(version=None)
        with pytest.raises(TypeError, match="Required version is None"):
            get_value(obj, "version", int, required=True)

    def test_unexpected_type(self):
        obj = Namespace(version="1")
        with pytest.raises(TypeError, match="version value is str, expected int"):
            get_value(obj, "version", int, required=True)

    @pytest.mark.parametrize(
        "path",
        [
            pytest.param(".[var]", id="variable"),
            pytest.param(".[1 + 2]", id="expression"),
            pytest.param("print('test')", id="function-call"),
        ],
    )
    def test_assertions(self, path: str):
        with pytest.raises(AssertionError):
            get_value(None, path, str)
