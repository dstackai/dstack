from typing import List, Union

from dstack._internal.backend.base.pricing import CatalogPricing
from dstack._internal.core.instance import InstanceType
from dstack._internal.hub.utils.catalog import read_catalog_csv


class GCPPricing(CatalogPricing):
    def __init__(self):
        super().__init__("gcp.csv")

    def fetch(self):
        for row in read_catalog_csv("gcp.csv"):
            instance_key = self.instance_key(row)
            region_spot = (row["location"][:-2], row["spot"] == "True")
            self.registry[instance_key][region_spot] = float(row["price"])

    @classmethod
    def instance_key(cls, instance: Union[dict, InstanceType]) -> str:
        # Some GPUs have the same instance name, we internally modify the name to include the GPU name and memory
        if isinstance(instance, InstanceType):
            if instance.resources.gpus:
                gpu = instance.resources.gpus[0]
                return f"{instance.instance_name}-{len(instance.resources.gpus)}x{gpu.name}-{gpu.memory_mib}"
            return instance.instance_name
        if int(instance["gpu_count"]) > 0:
            gpu_memory = round(float(instance["gpu_memory"]) * 1024)
            return f'{instance["instance_name"]}-{instance["gpu_count"]}x{instance["gpu_name"]}-{gpu_memory}'
        return instance["instance_name"]

    @classmethod
    def get_region(cls, row: dict) -> str:
        return row["location"][:-2]  # strip the zone suffix
