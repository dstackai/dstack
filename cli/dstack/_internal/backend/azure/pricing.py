import csv
from typing import Dict, Iterable, List, Optional

import pkg_resources

from dstack._internal.backend.base.pricing import Pricing
from dstack._internal.core.instance import InstanceType


class AzurePricing(Pricing):
    def _fetch(self):
        pricing_path = pkg_resources.resource_filename(
            "dstack._internal.backend", "resources/azure_pricing.csv"
        )
        with open(pricing_path, "r", newline="") as f:
            reader: Iterable[Dict[str, str]] = csv.DictReader(f)
            for row in reader:
                is_spot = {"True": True, "False": False}[row["spot"]]
                self.registry[row["instance_name"]][(row["location"], is_spot)] = float(
                    row["price"]
                )

    def fetch(self, instances: List[InstanceType], spot: Optional[bool]):
        if self._need_update("ondemand"):
            self._fetch()
