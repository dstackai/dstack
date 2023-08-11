from typing import List, Optional

from dstack._internal.backend.base.pricing import Pricing
from dstack._internal.core.instance import InstanceType


class LocalPricing(Pricing):
    def fetch(self, instances: List[InstanceType], spot: Optional[bool]):
        # empty instance_name and region
        self.registry[""][("", False)] = 0.0
