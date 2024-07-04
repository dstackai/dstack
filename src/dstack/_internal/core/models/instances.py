from enum import Enum
from typing import List, Optional

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.common import CoreModel
from dstack._internal.core.models.configurations import RegistryAuth
from dstack._internal.server.services.docker import DockerImage
from dstack._internal.utils.common import pretty_resources


class Gpu(CoreModel):
    name: str
    memory_mib: int


class Disk(CoreModel):
    size_mib: int


class Resources(CoreModel):
    cpus: int
    memory_mib: int
    gpus: List[Gpu]
    spot: bool
    disk: Disk = Disk(size_mib=102400)  # the default value (100GB) for backward compatibility
    description: str = ""

    def pretty_format(self) -> str:
        resources = {}
        if self.cpus > 0:
            resources["cpus"] = self.cpus
        if self.memory_mib > 0:
            resources["memory"] = f"{self.memory_mib / 1024:.0f}GB"
        if self.disk.size_mib > 0:
            resources["disk_size"] = f"{self.disk.size_mib / 1024:.1f}GB"
        if self.gpus:
            gpu = self.gpus[0]
            resources["gpu_name"] = gpu.name
            resources["gpu_count"] = len(self.gpus)
            if gpu.memory_mib > 0:
                resources["gpu_memory"] = f"{gpu.memory_mib / 1024:.0f}GB"
        return pretty_resources(**resources)


class InstanceType(CoreModel):
    name: str
    resources: Resources


class SSHConnectionParams(CoreModel):
    hostname: str
    username: str
    port: int


class SSHKey(CoreModel):
    public: str
    private: Optional[str] = None


class RemoteConnectionInfo(CoreModel):
    host: str
    port: int
    ssh_user: str
    ssh_keys: List[SSHKey]


class DockerConfig(CoreModel):
    registry_auth: Optional[RegistryAuth]
    image: Optional[DockerImage]


class InstanceConfiguration(CoreModel):
    project_name: str
    instance_name: str  # unique in pool
    instance_id: Optional[str] = None
    ssh_keys: List[SSHKey]
    job_docker_config: Optional[DockerConfig]
    user: str  # dstack user name
    availability_zone: Optional[str] = None

    def get_public_keys(self) -> List[str]:
        return [ssh_key.public.strip() for ssh_key in self.ssh_keys]


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


class InstanceOffer(CoreModel):
    backend: BackendType
    instance: InstanceType
    region: str
    price: float


class InstanceOfferWithAvailability(InstanceOffer):
    availability: InstanceAvailability
    instance_runtime: InstanceRuntime = InstanceRuntime.SHIM
