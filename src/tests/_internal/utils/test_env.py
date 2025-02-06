import pytest

from dstack._internal.utils.env import get_bool


@pytest.mark.parametrize(
    ["value", "expected"],
    [
        ["0", False],
        ["1", True],
        ["true", True],
        ["True", True],
        ["FALSE", False],
        ["off", False],
        ["ON", True],
    ],
)
def test_get_bool_is_set(monkeypatch: pytest.MonkeyPatch, value: str, expected: bool):
    monkeypatch.setenv("VAR", value)
    assert get_bool("VAR") is expected


def test_get_bool_not_set_default_not_set(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("VAR", raising=False)
    assert get_bool("VAR") is False


@pytest.mark.parametrize("default", [False, True])
def test_get_bool_not_set_default_is_set(monkeypatch: pytest.MonkeyPatch, default: bool):
    monkeypatch.delenv("VAR", raising=False)
    assert get_bool("VAR", default) is default


@pytest.mark.parametrize("value", ["", "2", "foo"])
def test_get_bool_error_value(monkeypatch: pytest.MonkeyPatch, value: str):
    monkeypatch.setenv("VAR", value)
    with pytest.raises(ValueError, match=f"VAR={value}"):
        assert get_bool("VAR")
