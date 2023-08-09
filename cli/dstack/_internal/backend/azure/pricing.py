import time
from typing import Dict, Optional

import requests

from dstack._internal.backend.base.pricing import DEFAULT_TTL, BasePricing
from dstack._internal.core.instance import InstanceType


class AzurePricing(BasePricing):
    def __init__(self):
        super().__init__()
        self.endpoint = "https://prices.azure.com/api/retail/prices"
        self.last_updated: Dict[str, float] = {}

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
                region_spot = (item["armRegionName"], "Spot" in item["meterName"])
                self.cache[item["armSkuName"]][region_spot] = item["retailPrice"]
            next_page = data["NextPageLink"]
            if not next_page:
                break
            data = requests.get(next_page).json()
        self.last_updated[query] = now

    def fetch(self, instance: InstanceType, spot: Optional[bool]):
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
