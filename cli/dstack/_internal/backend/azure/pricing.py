from typing import List, Optional

import requests

from dstack._internal.backend.base.pricing import Pricing
from dstack._internal.core.instance import InstanceType


class AzurePricing(Pricing):
    def __init__(self):
        super().__init__()
        self.endpoint = "https://prices.azure.com/api/retail/prices"

    def _fetch(self, query: str):
        r = requests.get(
            self.endpoint, params={"$filter": query, "api-version": "2021-10-01-preview"}
        )
        data = r.json()
        while True:
            for item in data["Items"]:
                region_spot = (item["armRegionName"], "Spot" in item["meterName"])
                self.registry[item["armSkuName"]][region_spot] = item["retailPrice"]
            next_page = data["NextPageLink"]
            if not next_page:
                break
            data = requests.get(next_page).json()

    def fetch(self, instances: List[InstanceType], spot: Optional[bool]):
        regions = set()
        instance_types = []
        for i in instances:
            if not i.available_regions:
                if self._need_update(i.instance_name):
                    instance_types.append(i.instance_name)
                continue
            for region in i.available_regions:
                if self._need_update(f"{i.instance_name}-{region}"):
                    instance_types.append(i.instance_name)
                    regions.add(region)
        if not instance_types:
            return

        regions = list(regions)
        for t in range(0, len(instance_types), 10):
            filters = [
                "serviceName eq 'Virtual Machines'",
                "priceType eq 'Consumption'",
                "(%s)" % " or ".join(f"armSkuName eq '{i}'" for i in instance_types[t : t + 10]),
            ]
            if not regions:
                self._fetch(" and ".join(filters))
                continue
            for r in range(0, len(regions), 5):
                regions_filter = "(%s)" % " or ".join(
                    f"armRegionName eq '{region}'" for region in regions[r : r + 5]
                )
                self._fetch(" and ".join(filters + [regions_filter]))
