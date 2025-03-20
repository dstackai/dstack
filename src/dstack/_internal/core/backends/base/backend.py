from abc import ABC, abstractmethod
from typing import ClassVar

from dstack._internal.core.backends.base.compute import Compute
from dstack._internal.core.models.backends.base import BackendType


class Backend(ABC):
    TYPE: ClassVar[BackendType]
    # `COMPUTE_CLASS` is used to introspect compute features without initializing it.
    COMPUTE_CLASS: ClassVar[type[Compute]]

    @abstractmethod
    def compute(self) -> Compute:
        """
        Returns Compute instance.
        """
        pass
