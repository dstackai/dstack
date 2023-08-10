import re
from collections import defaultdict
from typing import Dict, Optional

import google.cloud.billing_v1 as billing_v1
from google.oauth2 import service_account

from dstack._internal.backend.base.pricing import BasePricing, RegionSpot
from dstack._internal.core.instance import InstanceType

COMPUTE_SERVICE = "services/6F81-5844-456A"
VM_FAMILIES = {
    "A2 Instance": "a2",
    "E2 Instance": "e2",
    "G2 Instance": "g2",
    "Memory-optimized Instance": "m1",
    "N1 Predefined Instance": "n1",
}
GPU_FAMILIES = {
    "Nvidia Tesla A100": "A100",
    "Nvidia L4": "L4",
    "Nvidia Tesla P100": "P100",
    "Nvidia Tesla T4": "T4",
    "Nvidia Tesla V100": "V100",
}


class GCPPricing(BasePricing):
    def __init__(self, credentials: Optional[service_account.Credentials] = None):
        super().__init__()
        self.client = billing_v1.CloudCatalogClient(credentials=credentials)
        self.family_cache: Dict[str, Dict[str, Dict[RegionSpot, float]]] = {
            "ram": defaultdict(dict),
            "core": defaultdict(dict),
            "gpu": defaultdict(dict),
        }

    def _fetch_families(self):
        skus = self.client.list_skus(parent=COMPUTE_SERVICE)
        for sku in skus:
            if sku.category.resource_family != "Compute":
                continue
            if sku.category.usage_type not in ["OnDemand", "Preemptible"]:
                continue

            r = re.match(
                r"^(?:spot preemptible )?(.+) (gpu|ram|core)", sku.description, flags=re.IGNORECASE
            )
            if not r:
                continue
            family, resource = r.groups()
            if family in VM_FAMILIES:
                family = VM_FAMILIES[family]
            elif family in GPU_FAMILIES:
                family = GPU_FAMILIES[family]
            else:
                continue

            for region in sku.service_regions:
                region_spot = (region, sku.category.usage_type == "Preemptible")
                self.family_cache[resource.lower()][family][region_spot] = (
                    sku.pricing_info[0].pricing_expression.tiered_rates[0].unit_price.nanos / 1e9
                )

    def fetch(self, instance: InstanceType, spot: Optional[bool]):
        # todo cache
        self._fetch_families()

        vm_family = instance.instance_name.split("-")[0]
        gpu_family = None if not instance.resources.gpus else instance.resources.gpus[0].name
        region_spots = self.family_cache["core"].get(vm_family, {}).keys()
        region_spots &= self.family_cache["ram"].get(vm_family, {}).keys()
        if gpu_family:
            region_spots &= self.family_cache["gpu"].get(gpu_family, {}).keys()

        for region_spot in region_spots:
            cost = instance.resources.cpus * self.family_cache["core"][vm_family][region_spot]
            cost += (
                instance.resources.memory_mib
                / 1024
                * self.family_cache["ram"][vm_family][region_spot]
            )
            if gpu_family:
                cost += (
                    len(instance.resources.gpus)
                    * self.family_cache["gpu"][gpu_family][region_spot]
                )
            self.cache[instance.instance_name][region_spot] = cost
