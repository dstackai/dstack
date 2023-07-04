from typing import Optional

from dstack._internal.backend.base.compute import Compute, choose_instance_type
from dstack._internal.backend.local import runners
from dstack._internal.backend.local.config import LocalConfig
from dstack._internal.core.instance import InstanceType, LaunchedInstanceInfo
from dstack._internal.core.job import Job
from dstack._internal.core.request import RequestHead
from dstack._internal.core.runners import Runner


class LocalCompute(Compute):
    def __init__(self, backend_config: LocalConfig):
        self.backend_config = backend_config

    def get_request_head(self, job: Job, request_id: Optional[str]) -> RequestHead:
        return runners.get_request_head(job, request_id)

    def get_instance_type(self, job: Job) -> Optional[InstanceType]:
        resources = runners.check_runner_resources(self.backend_config, job.runner_id)
        instance_type = choose_instance_type(
            instance_types=[InstanceType(instance_name="", resources=resources)],
            requirements=job.requirements,
        )
        return instance_type

    def run_instance(self, job: Job, instance_type: InstanceType) -> LaunchedInstanceInfo:
        pid = runners.start_runner_process(self.backend_config, job.runner_id)
        return LaunchedInstanceInfo(request_id=pid, location=None)

    def terminate_instance(self, runner: Runner):
        runners.stop_process(runner.request_id)

    def cancel_spot_request(self, runner: Runner):
        runners.stop_process(runner.request_id)
