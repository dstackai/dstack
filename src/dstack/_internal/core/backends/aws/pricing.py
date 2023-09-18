from typing import List

from dstack._internal.core.backends.base.pricing import Pricing
from dstack._internal.core.models.instances import InstanceOffer


class AWSPricing(Pricing):
    def get_instances_offers(self) -> List[InstanceOffer]:
        pass
