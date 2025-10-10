from typing import Any, Protocol, TypeVar, Union

_T_contra = TypeVar("_T_contra", contravariant=True)


class SupportsDunderLT(Protocol[_T_contra]):
    def __lt__(self, other: _T_contra, /) -> bool: ...


class SupportsDunderGT(Protocol[_T_contra]):
    def __gt__(self, other: _T_contra, /) -> bool: ...


SupportsRichComparison = Union[SupportsDunderLT[Any], SupportsDunderGT[Any]]
