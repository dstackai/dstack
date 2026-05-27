from abc import ABC, abstractmethod
from typing import Generic, Optional, Sequence, Type, TypeVar

from dstack._internal.core.models.common import CoreModel

T = TypeVar("T", bound="BackendProfileOptions")


class BackendProfileOptions(CoreModel, ABC, Generic[T]):
    @abstractmethod
    def combine(self, other: T) -> T: ...


_OptionsT = TypeVar("_OptionsT", bound="BackendProfileOptions")


def get_backend_profile_options(
    options: Optional[Sequence[BackendProfileOptions]],
    options_type: Type[_OptionsT],
) -> Optional[_OptionsT]:
    if not options:
        return None
    return next((opt for opt in options if isinstance(opt, options_type)), None)
