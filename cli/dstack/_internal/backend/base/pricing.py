import time
from abc import ABC, abstractmethod
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from dstack._internal.core.instance import InstanceOffer, InstanceType

RegionSpot = Tuple[str, bool]
DEFAULT_TTL = 24 * 60 * 60  # 24 hours


class Pricing(ABC):
    def __init__(self):
        # instance_key -> { (region, spot) -> price }
        self.registry: Dict[str, Dict[RegionSpot, float]] = defaultdict(dict)
        self._last_updated: Dict[str, float] = {}

    def _need_update(self, key: str, ttl: int = DEFAULT_TTL):
        now = time.monotonic()
        if key not in self._last_updated or now - self._last_updated[key] > ttl:
            self._last_updated[key] = now
            return True
        return False

    @abstractmethod
    def fetch(self, instances: List[InstanceType], spot: Optional[bool]):
        # ignores instances[i].resources.spot
        pass

    def get_prices(
        self, instances: List[InstanceType], spot: Optional[bool] = None
    ) -> List[InstanceOffer]:
        """Estimate the cost in USD of running the specified instance for 1 hour in specified regions"""
        self.fetch(instances, spot)
        offers = []
        for instance in instances:
            for (region, is_spot), price in self.registry[self.instance_key(instance)].items():
                if not self.region_match(instance.available_regions, region):
                    continue
                if not self.spot_match(spot, is_spot):
                    continue
                i = instance.copy(deep=True)
                i.resources.spot = is_spot
                offers.append(InstanceOffer(i, region, price))
        return offers

    @classmethod
    def region_match(cls, available_regions: Optional[List[str]], region: str) -> bool:
        return not available_regions or region in available_regions

    @classmethod
    def spot_match(cls, requested: Optional[bool], spot: bool) -> bool:
        return requested is None or spot == requested

    @classmethod
    def instance_key(cls, instance: InstanceType) -> str:
        return instance.instance_name
