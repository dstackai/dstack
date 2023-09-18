from abc import ABC, abstractmethod
from typing import List

from dstack._internal.core.models.instances import InstanceOffer


class Pricing(ABC):
    @abstractmethod
    def get_instances_offers(self) -> List[InstanceOffer]:
        pass
