from enum import Enum
from typing import Union

import pytest

from dstack._internal.utils.env import Environ, _Value


class _TestEnviron:
    def get_environ(self, **env: str) -> Environ:
        return Environ(env)


class TestEnvironGetBool(_TestEnviron):
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
    def test_is_set(self, value: str, expected: bool):
        environ = self.get_environ(VAR=value)
        assert environ.get_bool("VAR") is expected

    def test_not_set_default_not_set(self):
        environ = self.get_environ()
        assert environ.get_bool("VAR") is None

    @pytest.mark.parametrize("default", [False, True])
    def test_not_set_default_is_set(self, default: bool):
        environ = self.get_environ()
        assert environ.get_bool("VAR", default=default) is default

    @pytest.mark.parametrize("value", ["", "2", "foo"])
    def test_error_bad_value(self, value: str):
        environ = self.get_environ(VAR=value)
        with pytest.raises(ValueError, match=f"VAR={value}"):
            environ.get_bool("VAR")


class TestEnvironGetInt(_TestEnviron):
    def test_is_set(self):
        environ = self.get_environ(VAR="12")
        assert environ.get_int("VAR") == 12

    def test_not_set_default_not_set(self):
        environ = self.get_environ()
        assert environ.get_int("VAR") is None

    def test_not_set_default_is_set(self):
        environ = self.get_environ()
        assert environ.get_int("VAR", default=12) == 12

    @pytest.mark.parametrize("value", ["", "false", "10a"])
    def test_error_bad_value(self, value: str):
        environ = self.get_environ(VAR=value)
        with pytest.raises(ValueError, match=f"VAR={value}"):
            environ.get_int("VAR")


class _Enum(Enum):
    FOO: Union[str, int]
    BAR: Union[str, int]


class _StrEnum(_Enum):
    FOO = "foo"
    BAR = "bar"


class _IntEnum(_Enum):
    FOO = 100
    BAR = 200


class TestEnvironGetEnum(_TestEnviron):
    @pytest.mark.parametrize(
        ["enum_cls", "value_type", "value"],
        [
            pytest.param(_StrEnum, str, "foo", id="str"),
            pytest.param(_IntEnum, int, "100", id="int"),
        ],
    )
    def test_is_set(self, enum_cls: type[_Enum], value_type: type[_Value], value: str):
        environ = self.get_environ(VAR=value)
        assert environ.get_enum("VAR", enum_cls, value_type=value_type) is enum_cls.FOO

    def test_not_set_default_not_set(self):
        environ = self.get_environ()
        assert environ.get_enum("VAR", _StrEnum) is None

    def test_not_set_default_is_set(self):
        environ = self.get_environ()
        assert environ.get_enum("VAR", _IntEnum, default=_IntEnum.BAR) is _IntEnum.BAR

    @pytest.mark.parametrize(
        ["enum_cls", "value_type", "value"],
        [
            pytest.param(_StrEnum, str, "baz", id="str"),
            pytest.param(_IntEnum, int, "300", id="int"),
            pytest.param(_IntEnum, int, "10a", id="invalid-int"),
        ],
    )
    def test_error_bad_value(self, enum_cls: type[_Enum], value_type: type[_Value], value: str):
        environ = self.get_environ(VAR=value)
        with pytest.raises(ValueError, match=f"VAR={value}"):
            environ.get_enum("VAR", enum_cls, value_type=value_type)
