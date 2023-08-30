import functools
import uuid
from typing import List, Optional

from dstack._internal.backend.base.compute import Compute, choose_instance_type
from dstack._internal.backend.local import runners
from dstack._internal.backend.local.config import LocalConfig
from dstack._internal.core.error import BackendValueError
from dstack._internal.core.instance import (
    InstanceOffer,
    InstancePricing,
    InstanceType,
    LaunchedInstanceInfo,
)
from dstack._internal.core.job import Job
from dstack._internal.core.request import RequestHead
from dstack._internal.core.runners import Runner


# TODO: The entire backend is deprecated and will be deleted in 0.11.x
class LocalCompute(Compute):
    def __init__(self, backend_config: LocalConfig):
        self.backend_config = backend_config

    def get_request_head(self, job: Job, request_id: Optional[str]) -> RequestHead:
        return runners.get_request_head(job, request_id)

    def get_instance_type(self, job: Job, region_name: Optional[str]) -> Optional[InstanceType]:
        resources = runners.check_runner_resources(self.backend_config, job.runner_id)
        instance_type = choose_instance_type(
            instance_types=[InstanceType(instance_name="", resources=resources)],
            requirements=job.requirements,
        )
        return instance_type

    @functools.lru_cache()
    def get_supported_instances(self) -> List[InstanceType]:
        resources = runners.check_runner_resources(self.backend_config, uuid.uuid4().hex)
        return [InstanceType(instance_name="", resources=resources, available_regions=[""])]

    def run_instance(
        self, job: Job, instance_type: InstanceType, region: str
    ) -> LaunchedInstanceInfo:
        pid = runners.start_runner_process(self.backend_config, job.runner_id)
        return LaunchedInstanceInfo(request_id=pid, location=None)

    def restart_instance(self, job: Job):
        if runners.get_container(job.run_name) is None:
            raise BackendValueError("Container not found")
        pid = runners.start_runner_process(self.backend_config, job.runner_id)
        return LaunchedInstanceInfo(request_id=pid, location=None)

    def terminate_instance(self, runner: Runner):
        runners.stop_process(runner.request_id)
        container_name = runner.job.instance_name or runner.job.run_name
        runners.remove_container(container_name)

    def cancel_spot_request(self, runner: Runner):
        pass

    def get_availability(self, offers: List[InstancePricing]) -> List[InstanceOffer]:
        raise NotImplementedError()
