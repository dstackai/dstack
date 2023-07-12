import os
from abc import ABC, abstractmethod
from functools import cmp_to_key
from typing import List, Optional

import dstack.version as version
from dstack._internal.core.error import DstackError
from dstack._internal.core.instance import InstanceType, LaunchedInstanceInfo
from dstack._internal.core.job import Job, Requirements
from dstack._internal.core.request import RequestHead
from dstack._internal.core.runners import Resources, Runner

WS_PORT = 10999


class ComputeError(DstackError):
    pass


class NoCapacityError(ComputeError):
    pass


class Compute(ABC):
    @abstractmethod
    def get_request_head(self, job: Job, request_id: Optional[str]) -> RequestHead:
        pass

    @abstractmethod
    def get_instance_type(self, job: Job) -> Optional[InstanceType]:
        pass

    @abstractmethod
    def run_instance(self, job: Job, instance_type: InstanceType) -> LaunchedInstanceInfo:
        pass

    @abstractmethod
    def terminate_instance(self, runner: Runner):
        pass

    @abstractmethod
    def cancel_spot_request(self, runner: Runner):
        pass


def choose_instance_type(
    instance_types: List[InstanceType],
    requirements: Optional[Requirements],
) -> Optional[InstanceType]:
    instance_types = _sort_instance_types(instance_types)
    eligible_instance_types = [
        instance_type
        for instance_type in instance_types
        if _matches_requirements(instance_type.resources, requirements)
    ]
    if len(eligible_instance_types) == 0:
        return None
    instance_type = eligible_instance_types[0]
    spot = False
    if requirements and requirements.spot:
        spot = True
    return InstanceType(
        instance_name=instance_type.instance_name,
        resources=Resources(
            cpus=instance_type.resources.cpus,
            memory_mib=instance_type.resources.memory_mib,
            gpus=instance_type.resources.gpus,
            spot=spot,
            local=False,
        ),
        available_regions=instance_type.available_regions,
    )


def _sort_instance_types(instance_types: List[InstanceType]) -> List[InstanceType]:
    return sorted(instance_types, key=cmp_to_key(_compare_instance_types))


def _compare_instance_types(i1, i2):
    r1_gpu_total_memory_mib = sum(map(lambda g: g.memory_mib, i1.resources.gpus or []))
    r2_gpu_total_memory_mib = sum(map(lambda g: g.memory_mib, i2.resources.gpus or []))
    if r1_gpu_total_memory_mib < r2_gpu_total_memory_mib:
        return -1
    elif r1_gpu_total_memory_mib > r2_gpu_total_memory_mib:
        return 1
    if i1.resources.cpus < i2.resources.cpus:
        return -1
    elif i1.resources.cpus > i2.resources.cpus:
        return 1
    if i1.resources.memory_mib < i2.resources.memory_mib:
        return -1
    elif i1.resources.memory_mib > i2.resources.memory_mib:
        return 1
    return 0


def _matches_requirements(resources: Resources, requirements: Optional[Requirements]) -> bool:
    if not requirements:
        return True
    if requirements.spot and not resources.spot:
        return False
    if requirements.cpus and requirements.cpus > resources.cpus:
        return False
    if requirements.memory_mib and requirements.memory_mib > resources.memory_mib:
        return False
    if requirements.gpus:
        gpu_count = requirements.gpus.count or 1
        if gpu_count > len(resources.gpus or []):
            return False
        if requirements.gpus.name and gpu_count > len(
            list(filter(lambda gpu: gpu.name == requirements.gpus.name, resources.gpus or []))
        ):
            return False
        if requirements.gpus.memory_mib and gpu_count > len(
            list(
                filter(
                    lambda gpu: gpu.memory_mib >= requirements.gpus.memory_mib,
                    resources.gpus or [],
                )
            )
        ):
            return False
    return True


def get_dstack_runner() -> str:
    if version.__is_release__:
        bucket = "dstack-runner-downloads"
        build = version.__version__
    else:  # stgn
        bucket = "dstack-runner-downloads-stgn"
        build = version.__version__ or os.environ.get("DSTACK_RUNNER_VERSION", "latest")

    commands = [
        f'sudo curl --output /usr/local/bin/dstack-runner "https://{bucket}.s3.eu-west-1.amazonaws.com/{build}/binaries/dstack-runner-linux-amd64"',
        f"sudo chmod +x /usr/local/bin/dstack-runner",
    ]
    return "\n".join(commands)
