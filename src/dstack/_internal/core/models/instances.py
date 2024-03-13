from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.configurations import RegistryAuth
from dstack._internal.server.services.docker import DockerImage
from dstack._internal.utils.common import pretty_resources


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
        resources = {
            "cpus": self.cpus,
            "memory": f"{self.memory_mib / 1024:g}GB",
            "disk_size": f"{self.disk.size_mib / 1024:g}GB",
        }
        if self.gpus:
            gpu = self.gpus[0]
            resources.update(
                gpu_name=gpu.name,
                gpu_count=len(self.gpus),
                gpu_memory=f"{gpu.memory_mib / 1024:g}GB",
            )
        return pretty_resources(**resources)


class InstanceType(BaseModel):
    name: str
    resources: Resources


class SSHConnectionParams(BaseModel):
    hostname: str
    username: str
    port: int


class SSHKey(BaseModel):
    public: str
    private: Optional[str] = None


class DockerConfig(BaseModel):
    registry_auth: Optional[RegistryAuth]
    image: Optional[DockerImage]


class InstanceConfiguration(BaseModel):
    project_name: str
    instance_name: str  # unique in pool
    ssh_keys: List[SSHKey]
    job_docker_config: Optional[DockerConfig]
    user: str  # dstack user name

    def get_public_keys(self) -> List[str]:
        return [ssh_key.public.strip() for ssh_key in self.ssh_keys]


class LaunchedInstanceInfo(BaseModel):
    instance_id: str
    region: str
    ip_address: str
    username: str
    ssh_port: int  # could be different from 22 for some backends
    dockerized: bool  # True if backend starts shim
    ssh_proxy: Optional[SSHConnectionParams] = Field(default=None)
    backend_data: Optional[str] = Field(default=None)  # backend-specific data in json


class InstanceRuntime(Enum):
    SHIM = "shim"
    RUNNER = "runner"


class InstanceAvailability(Enum):
    UNKNOWN = "unknown"
    AVAILABLE = "available"
    NOT_AVAILABLE = "not_available"
    NO_QUOTA = "no_quota"
    IDLE = "idle"
    BUSY = "busy"

    def is_available(self) -> bool:
        return self in {
            InstanceAvailability.UNKNOWN,
            InstanceAvailability.AVAILABLE,
            InstanceAvailability.IDLE,
        }


class InstanceOffer(BaseModel):
    backend: BackendType
    instance: InstanceType
    region: str
    price: float


class InstanceOfferWithAvailability(InstanceOffer):
    availability: InstanceAvailability
    instance_runtime: InstanceRuntime = InstanceRuntime.SHIM


class LaunchedGatewayInfo(BaseModel):
    instance_id: str
    ip_address: str
    region: str
