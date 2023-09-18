from typing import List

from dstack._internal.core.backends.base.pricing import Pricing
from dstack._internal.core.models.instances import InstanceOffer


class AWSPricing(Pricing):
    def get_instances_pricing(self) -> List[InstanceOffer]:
        pass
