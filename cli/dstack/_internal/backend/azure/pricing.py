import time
from typing import Dict, Optional

import requests

from dstack._internal.backend.base.pricing import BasePricing, RegionSpot
from dstack._internal.core.instance import InstanceType

DEFAULT_TTL = 24 * 60 * 60  # 24 hours


class AzurePricing(BasePricing):
    def __init__(self):
        self.endpoint = "https://prices.azure.com/api/retail/prices"
        # instance -> { region_spot -> price }
        self.cache: Dict[str, Dict[RegionSpot, float]] = {}
        self.last_updated: Dict[str, float] = {}

    def _put_instance(self, item: dict):
        name = item["armSkuName"]
        spot = "Spot" in item["meterName"]
        region = item["armRegionName"]
        if name not in self.cache:
            self.cache[name] = {}
        self.cache[name][(region, spot)] = item["retailPrice"]

    def _fetch(self, query: str, ttl: int = DEFAULT_TTL):
        now = time.time()
        if now - self.last_updated.get(query, 0) < ttl:
            return  # use cache
        r = requests.get(
            self.endpoint, params={"$filter": query, "api-version": "2021-10-01-preview"}
        )
        data = r.json()
        while True:
            for item in data["Items"]:
                self._put_instance(item)
            next_page = data["NextPageLink"]
            if not next_page:
                break
            data = requests.get(next_page).json()
        self.last_updated[query] = now

    def estimate_instance(
        self, instance: InstanceType, spot: Optional[bool] = None
    ) -> Dict[RegionSpot, float]:
        filters = [
            "serviceName eq 'Virtual Machines'",
            "priceType eq 'Consumption'",
            f"armSkuName eq '{instance.instance_name}'",
        ]
        if spot is True:
            filters.append("contains(meterName, 'Spot')")
        elif spot is False:
            filters.append("not contains(meterName, 'Spot')")
        if instance.available_regions:
            # TODO: split long lists in multiple fetches
            filters.append(
                "(%s)"
                % " or ".join(
                    f"armRegionName eq '{region}'" for region in sorted(instance.available_regions)
                )
            )
        self._fetch(" and ".join(filters))
        return {
            (r, s): v
            for (r, s), v in self.cache[instance.instance_name].items()
            if (not instance.available_regions or r in instance.available_regions)
            and (spot is None or spot is s)
        }
