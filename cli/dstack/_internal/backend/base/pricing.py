from abc import ABC, abstractmethod
from collections import defaultdict
from typing import Dict, List, Optional, Tuple, Union

from dstack._internal.core.instance import InstancePricing, InstanceType
from dstack._internal.core.runners import Gpu, Resources
from dstack._internal.hub.utils.catalog import read_catalog_csv

RegionSpot = Tuple[str, bool]


class Pricing(ABC):
    def __init__(self):
        # instance_key -> { (region, spot) -> price }
        self.registry: Dict[str, Dict[RegionSpot, float]] = defaultdict(dict)

    @abstractmethod
    def fetch(self):
        pass

    @abstractmethod
    def get_instances_pricing(self) -> List[InstancePricing]:
        pass

    def get_prices(  # TODO: deprecated?
        self, instances: List[InstanceType], spot: Optional[bool] = None
    ) -> List[InstancePricing]:
        """Estimate the cost in USD of running the specified instance for 1 hour in specified regions"""
        self.fetch()
        offers = []
        for instance in instances:
            for (region, is_spot), price in self.registry[self.instance_key(instance)].items():
                if not self.region_match(instance.available_regions, region):
                    continue
                if not self.spot_match(spot, is_spot):
                    continue
                i = instance.copy(deep=True)
                i.resources.spot = is_spot
                offers.append(InstancePricing(instance=i, region=region, price=price))
        return offers

    @classmethod
    def region_match(cls, available_regions: Optional[List[str]], region: str) -> bool:
        return not available_regions or region in available_regions

    @classmethod
    def spot_match(cls, requested: Optional[bool], spot: bool) -> bool:
        return requested is None or spot == requested

    @classmethod
    def instance_key(cls, instance: Union[dict, InstanceType]) -> str:
        if isinstance(instance, InstanceType):
            return instance.instance_name
        return instance["instance_name"]

    @classmethod
    def get_region(cls, row: dict) -> str:
        return row["location"]


class CatalogPricing(Pricing):
    def __init__(self, catalog_name: str):
        super().__init__()
        self.catalog_name = catalog_name

    def fetch(self):
        for row in read_catalog_csv(self.catalog_name):
            instance_key = self.instance_key(row)
            region_spot = (row["location"], row["spot"] == "True")
            self.registry[instance_key][region_spot] = float(row["price"])

    def get_instances_pricing(self) -> List[InstancePricing]:
        offers = {}
        for row in read_catalog_csv(self.catalog_name):
            offer = InstancePricing(
                instance=InstanceType(
                    instance_name=row["instance_name"],
                    resources=Resources(
                        cpus=int(row["cpu"]),
                        memory_mib=round(float(row["memory"]) * 1024),
                        gpus=get_gpus(row),
                        spot=row["spot"] == "True",
                        local=False,  # deprecated
                    ),
                ),
                region=self.get_region(row),
                price=float(row["price"]),
            )
            offers[
                (self.instance_key(offer.instance), offer.region, offer.instance.resources.spot)
            ] = offer
        return list(offers.values())


def get_gpus(row: dict) -> List[Gpu]:
    count = int(row["gpu_count"])
    if count == 0:
        return []
    return [
        Gpu(name=row["gpu_name"], memory_mib=round(float(row["gpu_memory"]) * 1024))
        for _ in range(count)
    ]
