from typing import List, Optional

from dstack._internal.backend.base.pricing import Pricing
from dstack._internal.core.instance import InstanceType

"""
Dumped on 2023-08-10 at https://cloud.lambdalabs.com/instances
```js
const selector = document.querySelector("[class^=_select-instance-type-step]")
const instances = selector.querySelectorAll("[class^=_instance-type-item]")
const prices = [...instances].map((i) => ({
    price: parseFloat(i.querySelector("[class^=_price]").textContent),
    name: i.querySelector("[class^=_request-button]")?.id || i.querySelector("[class^=_instance-type-title]").textContent,
}))
```
"""
PRICES = {
    "gpu_8x_h100_sxm5": 20.72,
    "gpu_1x_h100_pcie": 1.99,
    "gpu_8x_a100_80gb_sxm4": 12.0,
    "gpu_1x_a10": 0.6,
    "gpu_1x_rtx6000": 0.5,
    "gpu_1x_a100": 1.1,
    "gpu_1x_a100_sxm4": 1.1,
    "gpu_2x_a100": 2.2,
    "gpu_4x_a100": 4.4,
    "gpu_8x_a100": 8.8,
    "gpu_1x_a6000": 0.8,
    "gpu_2x_a6000": 1.6,
    "gpu_4x_a6000": 3.2,
    "gpu_8x_v100": 4.4,
}


class LambdaPricing(Pricing):
    def fetch(self, instances: List[InstanceType], spot: Optional[bool]):
        for instance in instances:
            for region in instance.available_regions:
                self.registry[instance.instance_name][(region, False)] = PRICES[
                    instance.instance_name
                ]
