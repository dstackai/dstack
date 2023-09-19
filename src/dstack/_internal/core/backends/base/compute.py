from abc import ABC, abstractmethod
from typing import List, Optional

from dstack._internal.core.models.instances import (
    InstanceOfferWithAvailability,
    InstanceState,
    LaunchedInstanceInfo,
)
from dstack._internal.core.models.runs import Job, Requirements, Run


class Compute(ABC):
    @abstractmethod
    def get_offers(
        self, requirements: Optional[Requirements] = None
    ) -> List[InstanceOfferWithAvailability]:
        pass

    @abstractmethod
    def get_instance_state(self, instance_id: str, region: str) -> InstanceState:
        pass

    @abstractmethod
    def terminate_instance(self, instance_id: str, region: str):
        pass

    @abstractmethod
    def run_job(
        self, run: Run, job: Job, instance_offer: InstanceOfferWithAvailability
    ) -> LaunchedInstanceInfo:
        pass

    # TODO
    # def create_gateway(
    #     self,
    #     instance_name: str,
    #     ssh_key_pub: str,
    #     region: str
    # ) -> GatewayHead:
    #     raise NotImplementedError()
