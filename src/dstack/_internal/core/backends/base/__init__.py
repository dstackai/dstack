from abc import abstractmethod

from dstack._internal.core.backends.base.compute import Compute
from dstack._internal.core.models.backends.base import BackendType


class Backend:
    TYPE: BackendType

    @abstractmethod
    def compute(self) -> Compute:
        pass
