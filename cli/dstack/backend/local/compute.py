from typing import Optional

from dstack.backend.base.compute import Compute
from dstack.backend.local import runners
from dstack.backend.local.config import LocalConfig
from dstack.core.instance import InstanceType
from dstack.core.job import Job
from dstack.core.request import RequestHead


class LocalCompute(Compute):
    def __init__(self, backend_config: LocalConfig):
        self.backend_config = backend_config

    def get_request_head(self, job: Job, request_id: Optional[str]) -> RequestHead:
        return runners.get_request_head(job, request_id)

    def get_instance_type(self, job: Job) -> Optional[InstanceType]:
        resources = runners.check_runner_resources(self.backend_config, job.runner_id)
        return InstanceType(instance_name="", resources=resources)

    def run_instance(self, job: Job, instance_type: InstanceType) -> str:
        return runners.start_runner_process(self.backend_config, job.runner_id)

    def terminate_instance(self, request_id: str):
        runners.stop_process(request_id)

    def cancel_spot_request(self, request_id: str):
        runners.stop_process(request_id)
