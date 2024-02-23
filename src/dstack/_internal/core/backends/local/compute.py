from typing import List, Optional

from dstack._internal.core.backends.base.compute import Compute
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import (
    InstanceAvailability,
    InstanceOfferWithAvailability,
    InstanceRuntime,
    InstanceType,
    LaunchedInstanceInfo,
    Resources,
)
from dstack._internal.core.models.runs import Job, Requirements, Run
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


class LocalCompute(Compute):
    def get_offers(
        self, requirements: Optional[Requirements] = None
    ) -> List[InstanceOfferWithAvailability]:
        return [
            InstanceOfferWithAvailability(
                backend=BackendType.LOCAL,
                instance=InstanceType(
                    name="local",
                    resources=Resources(cpus=4, memory_mib=8192, gpus=[], spot=False),
                ),
                region="local",
                price=0.00,
                availability=InstanceAvailability.AVAILABLE,
                instance_runtime=InstanceRuntime.RUNNER,
            )
        ]

    def terminate_instance(
        self, instance_id: str, region: str, backend_data: Optional[str] = None
    ):
        pass

    def create_instance(self, instance_offer, instance_config) -> LaunchedInstanceInfo:
        launched_instance = LaunchedInstanceInfo(
            instance_id="local",
            ip_address="127.0.0.1",
            region="",
            username="root",
            ssh_port=10022,
            dockerized=False,
            backend_data=None,
        )
        return launched_instance

    def run_job(
        self,
        run: Run,
        job: Job,
        instance_offer: InstanceOfferWithAvailability,
        project_ssh_public_key: str,
        project_ssh_private_key: str,
    ) -> LaunchedInstanceInfo:
        return LaunchedInstanceInfo(
            instance_id="local",
            ip_address="127.0.0.1",
            region="",
            username="root",
            ssh_port=10022,
            dockerized=False,
            ssh_proxy=None,
            backend_data=None,
        )
