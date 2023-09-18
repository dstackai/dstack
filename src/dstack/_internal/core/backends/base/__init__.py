from abc import abstractmethod

from dstack._internal.core.backends.base.compute import Compute


class Backend:
    @abstractmethod
    def compute(self) -> Compute:
        pass
