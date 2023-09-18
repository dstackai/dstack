from typing import List, Optional

from dstack._internal.core.backends.base.compute import Compute
from dstack._internal.core.models.instances import (
    InstanceOffer,
    InstanceOfferWithAvailability,
    LaunchedInstanceInfo,
)
from dstack._internal.core.models.runs import Job, Run


class AWSCompute(Compute):
    def get_availability(self, offers: List[InstanceOffer]) -> List[InstanceOfferWithAvailability]:
        pass

    def get_instance_state(
        self,
        instance_id: str,
        region: str,
        spot_request_id: Optional[str],
    ):
        pass

    def terminate_instance(
        self,
        instance_id: str,
        region: str,
        spot_request_id: Optional[str],
    ):
        pass

    def run_job(
        self,
        run: Run,
        job: Job,
        instance_offer: InstanceOfferWithAvailability,
    ) -> LaunchedInstanceInfo:
        pass
