import os
from collections.abc import Mapping
from enum import Enum
from typing import Callable, Optional, TypeVar, Union, overload

_EVT = Union[str, int]
_ET = TypeVar("_ET", bound=Enum)

_CVT = TypeVar("_CVT")


class Environ:
    def __init__(self, environ: Mapping[str, str]):
        self._environ = environ

    @overload
    def get(self, name: str, *, default: None = None) -> Optional[str]: ...

    @overload
    def get(self, name: str, *, default: str) -> str: ...

    def get(self, name: str, *, default: Optional[str] = None) -> Optional[str]:
        return self._environ.get(name, default)

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
        enum_cls: type[_ET],
        *,
        value_type: Optional[type[_EVT]] = None,
        default: None = None,
    ) -> Optional[_ET]: ...

    @overload
    def get_enum(
        self,
        name: str,
        enum_cls: type[_ET],
        *,
        value_type: Optional[type[_EVT]] = None,
        default: _ET,
    ) -> _ET: ...

    def get_enum(
        self,
        name: str,
        enum_cls: type[_ET],
        *,
        value_type: Optional[type[_EVT]] = None,
        default: Optional[_ET] = None,
    ) -> Optional[_ET]:
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

    @overload
    def get_callback(
        self, name: str, callback: Callable[[str], _CVT], *, default: None = None
    ) -> Optional[_CVT]: ...

    @overload
    def get_callback(
        self, name: str, callback: Callable[[str], _CVT], *, default: _CVT
    ) -> _CVT: ...

    def get_callback(
        self, name: str, callback: Callable[[str], _CVT], *, default: Optional[_CVT] = None
    ) -> Optional[_CVT]:
        try:
            raw_value = self._environ[name]
        except KeyError:
            return default
        try:
            return callback(raw_value)
        except ValueError as e:
            raise ValueError(f"Invalid value: {e}: {name}={raw_value}") from e


environ = Environ(os.environ)
