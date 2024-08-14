from abc import ABC, abstractmethod

from dstack._internal.core.backends.base.compute import Compute
from dstack._internal.core.models.backends.base import BackendType


class Backend(ABC):
    TYPE: BackendType

    @abstractmethod
    def compute(self) -> Compute:
        pass
