from typing import Callable, Optional, TypeVar

from dstack._internal.utils.typing import SupportsRichComparison

_T = TypeVar("_T")
_CompT = TypeVar("_CompT", bound=SupportsRichComparison)


class CombineError(ValueError):
    pass


def combine_optional(
    value1: Optional[_T], value2: Optional[_T], combiner: Callable[[_T, _T], _T]
) -> Optional[_T]:
    if value1 is None:
        return value2
    if value2 is None:
        return value1
    return combiner(value1, value2)


def get_max_optional(value1: Optional[_CompT], value2: Optional[_CompT]) -> Optional[_CompT]:
    return combine_optional(value1, value2, max)


def _get_single_value(value1: _T, value2: _T) -> _T:
    if value1 == value2:
        return value1
    raise CombineError(f"Values {value1!r} and {value2!r} cannot be combined")


def get_single_value_optional(value1: Optional[_T], value2: Optional[_T]) -> Optional[_T]:
    return combine_optional(value1, value2, _get_single_value)
