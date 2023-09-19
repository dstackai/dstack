from abc import abstractmethod
from datetime import datetime
from typing import List, Optional

from dstack._internal.core.backends.base.compute import Compute


class Backend:
    TYPE: BackendType

    @abstractmethod
    def compute(self) -> Compute:
        pass
