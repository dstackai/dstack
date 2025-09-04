import os
from collections.abc import Mapping
from enum import Enum
from typing import Optional, TypeVar, Union, overload

_Value = Union[str, int]
_T = TypeVar("_T", bound=Enum)


class Environ:
    def __init__(self, environ: Mapping[str, str]):
        self._environ = environ

    @overload
    def get_bool(self, name: str, *, default: None = None) -> Optional[bool]: ...

    @overload
    def get_bool(self, name: str, *, default: bool) -> bool: ...

    def get_bool(self, name: str, *, default: Optional[bool] = None) -> Optional[bool]:
        try:
            raw_value = self._environ[name]
        except KeyError:
            return default
        value = raw_value.lower()
        if value in ["0", "false", "off"]:
            return False
        if value in ["1", "true", "on"]:
            return True
        raise ValueError(f"Invalid bool value: {name}={raw_value}")

    @overload
    def get_int(self, name: str, *, default: None = None) -> Optional[int]: ...

    @overload
    def get_int(self, name: str, *, default: int) -> int: ...

    def get_int(self, name: str, *, default: Optional[int] = None) -> Optional[int]:
        try:
            raw_value = self._environ[name]
        except KeyError:
            return default
        try:
            return int(raw_value)
        except ValueError as e:
            raise ValueError(f"Invalid int value: {e}: {name}={raw_value}") from e

    @overload
    def get_enum(
        self,
        name: str,
        enum_cls: type[_T],
        *,
        value_type: Optional[type[_Value]] = None,
        default: None = None,
    ) -> Optional[_T]: ...

    @overload
    def get_enum(
        self,
        name: str,
        enum_cls: type[_T],
        *,
        value_type: Optional[type[_Value]] = None,
        default: _T,
    ) -> _T: ...

    def get_enum(
        self,
        name: str,
        enum_cls: type[_T],
        *,
        value_type: Optional[type[_Value]] = None,
        default: Optional[_T] = None,
    ) -> Optional[_T]:
        try:
            raw_value = self._environ[name]
        except KeyError:
            return default
        try:
            if value_type is not None:
                raw_value = value_type(raw_value)
            return enum_cls(raw_value)
        except (ValueError, TypeError) as e:
            raise ValueError(f"Invalid {enum_cls.__name__} value: {e}: {name}={raw_value}") from e


environ = Environ(os.environ)
