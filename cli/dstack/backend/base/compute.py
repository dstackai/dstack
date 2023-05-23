from abc import ABC, abstractmethod
from functools import cmp_to_key
from typing import List, Optional

from dstack.core.instance import InstanceType
from dstack.core.job import Job, Requirements
from dstack.core.request import RequestHead
from dstack.core.runners import Resources

WS_PORT = 10999


class ComputeError(Exception):
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
    def run_instance(self, job: Job, instance_type: InstanceType) -> str:
        pass

    @abstractmethod
    def terminate_instance(self, request_id: str):
        pass

    @abstractmethod
    def cancel_spot_request(self, request_id: str):
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
    interruptible = False
    if requirements and requirements.interruptible:
        interruptible = True
    return InstanceType(
        instance_name=instance_type.instance_name,
        resources=Resources(
            cpus=instance_type.resources.cpus,
            memory_mib=instance_type.resources.memory_mib,
            gpus=instance_type.resources.gpus,
            interruptible=interruptible,
            local=False,
        ),
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
        if requirements.interruptible and not resources.interruptible:
            return False
    return True
