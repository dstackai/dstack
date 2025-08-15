import datetime
from enum import Enum
from typing import Dict, List, Optional
from uuid import UUID

import gpuhunt
from pydantic import root_validator

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.common import CoreModel
from dstack._internal.core.models.envs import Env
from dstack._internal.core.models.health import HealthStatus
from dstack._internal.core.models.volumes import Volume
from dstack._internal.utils.common import pretty_resources


class Gpu(CoreModel):
    name: str
    memory_mib: int
    # Although it's declared as Optional, in fact it always has a value set by the root validator,
    # that is, `assert gpu.vendor is not None` should be a safe type narrowing.
    vendor: Optional[gpuhunt.AcceleratorVendor] = None

    @root_validator(pre=True)
    def validate_name_and_vendor(cls, values):
        is_tpu = False
        name = values.get("name")
        if name and name.startswith("tpu-"):
            is_tpu = True
            values["name"] = name[4:]
        vendor = values.get("vendor")
        if vendor is None:
            if is_tpu:
                values["vendor"] = gpuhunt.AcceleratorVendor.GOOGLE
            else:
                values["vendor"] = gpuhunt.AcceleratorVendor.NVIDIA
        else:
            values["vendor"] = gpuhunt.AcceleratorVendor.cast(vendor)
        return values


class Disk(CoreModel):
    size_mib: int


class Resources(CoreModel):
    cpus: int
    memory_mib: int
    gpus: List[Gpu]
    spot: bool
    disk: Disk = Disk(size_mib=102400)  # the default value (100GB) for backward compatibility
    # TODO: make description a computed field after migrating to pydanticV2
    description: str = ""
    cpu_arch: Optional[gpuhunt.CPUArchitecture] = None

    @root_validator
    def _description(cls, values) -> Dict:
        try:
            description = values["description"]
            if not description:
                cpus = values["cpus"]
                memory_mib = values["memory_mib"]
                gpus = values["gpus"]
                disk_size_mib = values["disk"].size_mib
                spot = values["spot"]
                cpu_arch = values["cpu_arch"]
                values["description"] = Resources._pretty_format(
                    cpus, cpu_arch, memory_mib, disk_size_mib, gpus, spot, include_spot=True
                )
        except KeyError:
            return values
        return values

    @staticmethod
    def _pretty_format(
        cpus: int,
        cpu_arch: Optional[gpuhunt.CPUArchitecture],
        memory_mib: int,
        disk_size_mib: int,
        gpus: List[Gpu],
        spot: bool,
        include_spot: bool = False,
    ) -> str:
        resources = {}
        if cpus > 0:
            resources["cpus"] = cpus
            resources["cpu_arch"] = cpu_arch
        if memory_mib > 0:
            resources["memory"] = f"{memory_mib / 1024:.0f}GB"
        if disk_size_mib > 0:
            resources["disk_size"] = f"{disk_size_mib / 1024:.0f}GB"
        if gpus:
            gpu = gpus[0]
            resources["gpu_name"] = gpu.name
            resources["gpu_count"] = len(gpus)
            if gpu.memory_mib > 0:
                resources["gpu_memory"] = f"{gpu.memory_mib / 1024:.0f}GB"
        output = pretty_resources(**resources)
        if include_spot and spot:
            output += " (spot)"
        return output

    def pretty_format(self, include_spot: bool = False) -> str:
        return Resources._pretty_format(
            self.cpus,
            self.cpu_arch,
            self.memory_mib,
            self.disk.size_mib,
            self.gpus,
            self.spot,
            include_spot,
        )


class InstanceType(CoreModel):
    name: str
    resources: Resources


class SSHConnectionParams(CoreModel):
    hostname: str
    username: str
    port: int

    class Config(CoreModel.Config):
        frozen = True


class SSHKey(CoreModel):
    public: str
    private: Optional[str] = None


class RemoteConnectionInfo(CoreModel):
    host: str
    port: int
    ssh_user: str
    ssh_keys: List[SSHKey]
    ssh_proxy: Optional[SSHConnectionParams] = None
    ssh_proxy_keys: Optional[list[SSHKey]] = None
    env: Env = Env()


class InstanceConfiguration(CoreModel):
    project_name: str
    instance_name: str
    user: str  # dstack user name
    ssh_keys: List[SSHKey]
    instance_id: Optional[str] = None
    reservation: Optional[str] = None
    volumes: Optional[List[Volume]] = None
    tags: Optional[Dict[str, str]] = None

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
    NO_BALANCE = (
        "no_balance"  # Introduced in 0.19.24, may be used after a short compatibility period
    )
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
    availability_zones: Optional[List[str]] = None
    instance_runtime: InstanceRuntime = InstanceRuntime.SHIM
    blocks: int = 1
    total_blocks: int = 1


class InstanceStatus(str, Enum):
    PENDING = "pending"
    PROVISIONING = "provisioning"
    IDLE = "idle"
    BUSY = "busy"
    TERMINATING = "terminating"
    TERMINATED = "terminated"

    def is_available(self) -> bool:
        return self in (
            self.IDLE,
            self.BUSY,
        )

    def is_active(self) -> bool:
        return self not in self.finished_statuses()

    @classmethod
    def finished_statuses(cls) -> List["InstanceStatus"]:
        return [cls.TERMINATING, cls.TERMINATED]


class Instance(CoreModel):
    id: UUID
    project_name: str
    backend: Optional[BackendType] = None
    instance_type: Optional[InstanceType] = None
    name: str
    fleet_id: Optional[UUID] = None
    fleet_name: Optional[str] = None
    instance_num: int
    job_name: Optional[str] = None  # deprecated, always None (instance can have more than one job)
    hostname: Optional[str] = None
    status: InstanceStatus
    unreachable: bool = False
    health_status: HealthStatus = HealthStatus.HEALTHY
    termination_reason: Optional[str] = None
    created: datetime.datetime
    region: Optional[str] = None
    availability_zone: Optional[str] = None
    price: Optional[float] = None
    total_blocks: Optional[int] = None
    busy_blocks: int = 0
