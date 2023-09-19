from abc import abstractmethod
from typing import List

from dstack._internal.core.backends.base.compute import Compute
from dstack._internal.core.models.instances import InstanceOfferWithAvailability
from dstack._internal.core.models.profiles import BackendType, SpotPolicy
from dstack._internal.core.models.runs import Requirements


class Backend:
    TYPE: BackendType

    @abstractmethod
    def compute(self) -> Compute:
        pass

    def get_instance_candidates(
        self, requirements: Requirements
    ) -> List[InstanceOfferWithAvailability]:
        return self.compute().get_offers(requirements)
