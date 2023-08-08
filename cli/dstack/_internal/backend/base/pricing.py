from abc import ABC, abstractmethod
from typing import Dict, Optional, Tuple

from dstack._internal.core.instance import InstanceType

RegionSpot = Tuple[str, bool]


class BasePricing(ABC):
    @abstractmethod
    def estimate_instance(
        self, instance: InstanceType, spot: Optional[bool] = None
    ) -> Dict[RegionSpot, float]:
        """Estimate the cost in USD of running the specified instance for 1 hour in specified regions"""
        pass
