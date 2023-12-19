from enum import Enum
from typing import List, Optional

from pydantic import BaseModel

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.utils.common import pretty_resources


class InstanceState(str, Enum):
    NOT_FOUND = "not_found"
    PROVISIONING = "provisioning"
    RUNNING = "running"
    STOPPED = "stopped"
    STOPPING = "stopping"
    TERMINATED = "terminated"


class Gpu(BaseModel):
    name: str
    memory_mib: int


class Disk(BaseModel):
    size_mib: int


class Resources(BaseModel):
    cpus: int
    memory_mib: int
    gpus: List[Gpu]
    spot: bool
    disk: Disk = Disk(size_mib=102400)  # the default value (100GB) for backward compatibility
    description: str = ""

    def pretty_format(self) -> str:
        if not self.gpus:
            return pretty_resources(
                cpus=self.cpus, memory=self.memory_mib, disk_size=self.disk.size_mib
            )
        return pretty_resources(
            cpus=self.cpus,
            memory=self.memory_mib,
            gpu_count=len(self.gpus),
            gpu_name=self.gpus[0].name,
            gpu_memory=self.gpus[0].memory_mib,
            disk_size=self.disk.size_mib,
        )


class InstanceType(BaseModel):
    name: str
    resources: Resources


class LaunchedInstanceInfo(BaseModel):
    instance_id: str
    ip_address: str
    region: str
    username: str
    ssh_port: int  # could be different from 22 for some backends
    dockerized: bool  # True if JumpProxy is needed
    backend_data: Optional[str]  # backend-specific data in json


class InstanceAvailability(Enum):
    UNKNOWN = "unknown"
    AVAILABLE = "available"
    NOT_AVAILABLE = "not_available"
    NO_QUOTA = "no_quota"


class InstanceOffer(BaseModel):
    backend: BackendType
    instance: InstanceType
    region: str
    price: float


class InstanceOfferWithAvailability(InstanceOffer):
    availability: InstanceAvailability


class LaunchedGatewayInfo(BaseModel):
    instance_id: str
    ip_address: str
    region: str
