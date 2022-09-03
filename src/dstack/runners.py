from typing import Optional, List

from dstack.jobs import Job


class Gpu:
    def __init__(self, name: str, memory_mib: int):
        self.memory_mib = memory_mib
        self.name = name

    def __str__(self) -> str:
        return f'Gpu(name="{self.name}", memory_mib={self.memory_mib})'


class Resources:
    def __init__(self, cpus: int, memory_mib: int, gpus: Optional[List[Gpu]], interruptible: bool):
        self.cpus = cpus
        self.memory_mib = memory_mib
        self.gpus = gpus
        self.interruptible = interruptible

    def __str__(self) -> str:
        return f'Resources(cpus={self.cpus}, memory_mib={self.memory_mib}, ' \
               f'gpus=[{", ".join(map(lambda g: str(g), self.gpus))}], ' \
               f'interruptible={self.interruptible})'


class Runner:
    def __init__(self, runner_id: str, request_id: Optional[str], resources: Resources,
                 job: Job, secret_names: List[str]):
        self.runner_id = runner_id
        self.request_id = request_id
        self.job = job
        self.resources = resources
        self.secret_names = secret_names
