from typing import List, Optional

from dstack._internal.core.backends.base.compute import Compute
from dstack._internal.core.backends.oci.config import OCIConfig
from dstack._internal.core.models.instances import InstanceOfferWithAvailability
from dstack._internal.core.models.runs import Job, JobProvisioningData, Requirements, Run


class OCICompute(Compute):
    def __init__(self, config: OCIConfig):
        self.config = config

    def get_offers(
        self, requirements: Optional[Requirements] = None
    ) -> List[InstanceOfferWithAvailability]:
        raise NotImplementedError

    def run_job(
        self,
        run: Run,
        job: Job,
        instance_offer: InstanceOfferWithAvailability,
        project_ssh_public_key: str,
        project_ssh_private_key: str,
    ) -> JobProvisioningData:
        raise NotImplementedError

    def terminate_instance(
        self, instance_id: str, region: str, backend_data: Optional[str] = None
    ) -> None:
        raise NotImplementedError
