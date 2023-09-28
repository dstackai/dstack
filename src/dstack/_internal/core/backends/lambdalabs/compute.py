from typing import List, Optional

from dstack._internal.core.backends.base.compute import Compute
from dstack._internal.core.backends.lambdalabs.config import LambdaConfig
from dstack._internal.core.models.instances import (
    InstanceOfferWithAvailability,
    InstanceState,
    LaunchedInstanceInfo,
)
from dstack._internal.core.models.runs import Job, Requirements, Run


class LambdaCompute(Compute):
    def __init__(self, config: LambdaConfig):
        self.config = config

    def get_offers(
        self, requirements: Optional[Requirements] = None
    ) -> List[InstanceOfferWithAvailability]:
        pass

    def get_instance_state(self, instance_id: str, region: str) -> InstanceState:
        pass

    def terminate_instance(self, instance_id: str, region: str):
        pass

    def run_job(
        self,
        run: Run,
        job: Job,
        instance_offer: InstanceOfferWithAvailability,
        project_ssh_public_key: str,
    ) -> LaunchedInstanceInfo:
        pass
