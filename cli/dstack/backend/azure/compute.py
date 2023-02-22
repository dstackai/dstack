from typing import Optional

from azure.core.credentials import TokenCredential
from azure.mgmt.compute import ComputeManagementClient

from dstack.backend.azure import runners
from dstack.backend.base.compute import Compute
from dstack.core.instance import InstanceType
from dstack.core.job import Job
from dstack.core.request import RequestHead


class AzureCompute(Compute):
    def __init__(self, credential: TokenCredential, subscription_id: str):
        self._compute_management_client = ComputeManagementClient(
            credential=credential, subscription_id=subscription_id
        )

    def cancel_spot_request(self, request_id: str):
        raise NotImplementedError

    def terminate_instance(self, request_id: str):
        raise NotImplementedError

    def get_instance_type(self, job: Job) -> Optional[InstanceType]:
        instance_types = runners._get_instance_types(client=self._compute_management_client)
        instance_types.sort(key=runners._key_for_instance)
        return runners._get_instance_type(
            instance_types=instance_types, requirements=job.requirements
        )

    def run_instance(self, job: Job, instance_type: InstanceType) -> str:
        raise NotImplementedError(job, instance_type)

    def get_request_head(self, job: Job, request_id: Optional[str]) -> RequestHead:
        raise NotImplementedError
