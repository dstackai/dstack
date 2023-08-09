from abc import ABC, abstractmethod
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from dstack._internal.core.instance import InstanceType

RegionSpot = Tuple[str, bool]
DEFAULT_TTL = 24 * 60 * 60  # 24 hours


class BasePricing(ABC):
    def __init__(self):
        # instance -> { region_spot -> price }
        self.cache: Dict[str, Dict[RegionSpot, float]] = defaultdict(dict)

    @abstractmethod
    def fetch(self, instance: InstanceType, spot: Optional[bool]):
        pass

    def estimate_instance(
        self, instance: InstanceType, spot: Optional[bool] = None
    ) -> Dict[RegionSpot, float]:
        """Estimate the cost in USD of running the specified instance for 1 hour in specified regions"""
        self.fetch(instance, spot)
        return {
            (r, s): v
            for (r, s), v in self.cache[instance.instance_name].items()
            if self.region_match(instance.available_regions, r) and self.spot_match(spot, s)
        }

    @classmethod
    def region_match(cls, regions: Optional[List[str]], region: str) -> bool:
        return not regions or region in regions

    @classmethod
    def spot_match(cls, requested: Optional[bool], spot: bool) -> bool:
        return requested is None or spot == requested
