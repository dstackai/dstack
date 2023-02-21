from typing import Optional

from dstack.backend.base.compute import Compute
from dstack.core.instance import InstanceType
from dstack.core.job import Job
from dstack.core.request import RequestHead


class AzureCompute(Compute):
    def cancel_spot_request(self, request_id: str):
        raise NotImplementedError

    def terminate_instance(self, request_id: str):
        raise NotImplementedError

    def get_instance_type(self, job: Job) -> Optional[InstanceType]:
        raise NotImplementedError

    def run_instance(self, job: Job, instance_type: InstanceType) -> str:
        raise NotImplementedError

    def get_request_head(self, job: Job, request_id: Optional[str]) -> RequestHead:
        raise NotImplementedError
