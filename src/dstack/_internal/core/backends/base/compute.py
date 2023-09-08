from abc import ABC, abstractmethod
from typing import List, Optional

from dstack._internal.core.models.instances import (
    InstanceOffer,
    InstanceOfferWithAvailability,
    InstanceType,
    LaunchedInstanceInfo,
)
from dstack._internal.core.models.runs import Job, Run


class Compute(ABC):
    @abstractmethod
    def get_availability(self, offers: List[InstanceOffer]) -> List[InstanceOfferWithAvailability]:
        pass

    @abstractmethod
    def get_instance_state(
        self,
        instance_id: str,
        region: str,
        spot_request_id: Optional[str],
    ):
        pass

    @abstractmethod
    def terminate_instance(
        self,
        instance_id: str,
        region: str,
        spot_request_id: Optional[str],
    ):
        pass

    @abstractmethod
    def run_job(
        self,
        run: Run,
        job: Job,
        instance_offer: InstanceOfferWithAvailability,
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
