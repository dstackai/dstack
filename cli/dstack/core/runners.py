from typing import Optional, List

from dstack.core.job import Job


class Gpu:
    def __init__(self, name: str, memory_mib: int):
        self.memory_mib = memory_mib
        self.name = name

    def __str__(self) -> str:
        return f'Gpu(name="{self.name}", memory_mib={self.memory_mib})'


class Resources:
    def __init__(
        self,
        cpus: int,
        memory_mib: int,
        gpus: Optional[List[Gpu]],
        interruptible: bool,
        local: bool,
    ):
        self.cpus = cpus
        self.memory_mib = memory_mib
        self.gpus = gpus
        self.interruptible = interruptible
        self.local = local

    def __str__(self) -> str:
        return (
            f"Resources(cpus={self.cpus}, memory_mib={self.memory_mib}, "
            f'gpus=[{", ".join(map(lambda g: str(g), self.gpus))}], '
            f"interruptible={self.interruptible}, "
            f"local={self.local})"
        )


class Runner:
    def __init__(self, runner_id: str, request_id: Optional[str], resources: Resources, job: Job):
        self.runner_id = runner_id
        self.request_id = request_id
        self.job = job
        self.resources = resources

    def serialize(self) -> dict:
        resources = {
            "cpus": self.resources.cpus,
            "memory_mib": self.resources.memory_mib,
            "gpus": [
                {
                    "name": gpu.name,
                    "memory_mib": gpu.memory_mib,
                }
                for gpu in (self.resources.gpus or [])
            ],
            "interruptible": self.resources.interruptible is True,
            "local": self.resources.local is True,
        }
        data = {
            "runner_id": self.runner_id,
            "request_id": self.request_id,
            "resources": resources,
            "job": self.job.serialize(),
        }
        return data

    @staticmethod
    def unserialize(data: dict):
        return Runner(
            data["runner_id"],
            data.get("request_id"),
            Resources(
                data["resources"]["cpus"],
                data["resources"]["memory_mib"],
                [Gpu(g["name"], g["memory_mib"]) for g in data["resources"]["gpus"]],
                data["resources"]["interruptible"] is True,
                data["resources"].get("local") is True,
            ),
            Job.unserialize(data["job"]),
        )
