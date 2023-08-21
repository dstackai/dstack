from typing import List, Optional

from dstack._internal.backend.base.pricing import Pricing
from dstack._internal.core.instance import InstanceType
from dstack._internal.hub.utils.catalog import read_catalog_csv


class GCPPricing(Pricing):
    def _fetch_catalog(self):
        for row in read_catalog_csv("gcp.csv"):
            instance_key = row["instance_name"]
            if int(row["gpu_count"]) > 0:
                gpu_memory = round(float(row["gpu_memory"]) * 1024)
                instance_key += f'-{row["gpu_count"]}x{row["gpu_name"]}-{gpu_memory}'
            self.registry[instance_key][(row["location"][:-2], row["spot"] == "True")] = float(
                row["price"]
            )

    def fetch(self, instances: List[InstanceType], spot: Optional[bool]):
        if self._need_update("catalog"):
            self._fetch_catalog()

    @classmethod
    def instance_key(cls, instance: InstanceType) -> str:
        if instance.resources.gpus:
            gpu = instance.resources.gpus[0]
            return f"{instance.instance_name}-{len(instance.resources.gpus)}x{gpu.name}-{gpu.memory_mib}"
        return instance.instance_name
