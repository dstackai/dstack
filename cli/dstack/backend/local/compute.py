from typing import Optional, Tuple

from dstack.backend.base.compute import Compute
from dstack.backend.local import runners
from dstack.core.instance import InstanceType
from dstack.core.job import Job, Requirements
from dstack.core.request import RequestHead


class LocalCompute(Compute):
    def get_request_head(self, job: Job, request_id: Optional[str]) -> RequestHead:
        return runners.get_request_head(job, request_id)

    def get_instance_type(self, job: Job) -> Optional[InstanceType]:
        resources = runners.check_runner_resources(job.runner_id)
        return InstanceType(instance_name="local_runner", resources=resources)

    def run_instance(self, job: Job, instance_type: InstanceType) -> str:
        return runners.start_runner_process(job.runner_id)

    def terminate_instance(self, request_id: str):
        runners.stop_process(request_id)

    def cancel_spot_request(self, request_id: str):
        runners.stop_process(request_id)
