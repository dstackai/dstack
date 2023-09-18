from abc import abstractmethod
from datetime import datetime
from typing import List, Optional

from dstack._internal.core.backends.base.compute import Compute
from dstack._internal.core.backends.base.pricing import Pricing
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import (
    InstanceOffer,
    InstanceOfferWithAvailability,
    Resources,
)
from dstack._internal.core.models.profiles import SpotPolicy
from dstack._internal.core.models.runs import Requirements
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


class Backend:
    TYPE: BackendType

    @abstractmethod
    def compute(self) -> Compute:
        pass

    @abstractmethod
    def pricing(self) -> Pricing:
        pass

    def get_instance_candidates(
        self, requirements: Requirements, spot_policy: SpotPolicy
    ) -> List[InstanceOfferWithAvailability]:
        start = datetime.now()
        offers = self.pricing().get_instances_offers()

        if requirements.max_price is not None:
            offers = [i for i in offers if i.price <= requirements.max_price]
        offers = [i for i in offers if _matches_requirements(i.instance.resources, requirements)]
        if spot_policy != SpotPolicy.AUTO:
            offers = [
                i for i in offers if i.instance.resources.spot == (spot_policy == SpotPolicy.SPOT)
            ]

        offers = self.compute().get_availability(offers)
        logger.debug("[%s] got instance candidates in %s", self.TYPE, datetime.now() - start)
        return offers


def _matches_requirements(resources: Resources, requirements: Optional[Requirements]) -> bool:
    if not requirements:
        return True
    if requirements.spot and not resources.spot:
        return False
    if requirements.cpus and requirements.cpus > resources.cpus:
        return False
    if requirements.memory_mib and requirements.memory_mib > resources.memory_mib:
        return False
    if requirements.gpus:
        gpu_count = requirements.gpus.count or 1
        if gpu_count > len(resources.gpus or []):
            return False
        if requirements.gpus.name and gpu_count > len(
            list(filter(lambda gpu: gpu.name == requirements.gpus.name, resources.gpus or []))
        ):
            return False
        if requirements.gpus.memory_mib and gpu_count > len(
            list(
                filter(
                    lambda gpu: gpu.memory_mib >= requirements.gpus.memory_mib,
                    resources.gpus or [],
                )
            )
        ):
            return False
    return True
