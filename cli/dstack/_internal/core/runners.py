from typing import List, Optional

from pydantic import BaseModel

from dstack._internal.core.job import Job


class Gpu(BaseModel):
    name: str
    memory_mib: int


class Resources(BaseModel):
    cpus: int
    memory_mib: int
    gpus: Optional[List[Gpu]]
    spot: bool
    local: bool


class Runner(BaseModel):
    runner_id: str
    request_id: Optional[str]
    resources: Resources
    job: Job

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
            "spot": self.resources.spot is True,
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
            runner_id=data["runner_id"],
            request_id=data.get("request_id"),
            resources=Resources(
                cpus=data["resources"]["cpus"],
                memory_mib=data["resources"]["memory_mib"],
                gpus=[
                    Gpu(name=g["name"], memory_mib=g["memory_mib"])
                    for g in data["resources"]["gpus"]
                ],
                spot=data["resources"].get("spot")
                or data["resources"].get("interruptible")
                or False,
                local=data["resources"].get("local") or False,
            ),
            job=Job.unserialize(data["job"]),
        )
