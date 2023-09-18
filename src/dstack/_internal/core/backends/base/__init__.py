from abc import abstractmethod

from dstack._internal.core.backends.base.compute import Compute
from dstack._internal.core.backends.base.pricing import Pricing


class Backend:
    @abstractmethod
    def compute(self) -> Compute:
        pass

    @abstractmethod
    def pricing(self) -> Pricing:
        pass
