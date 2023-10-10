from enum import Enum
from typing import List, Optional

from pydantic import BaseModel

from dstack._internal.core.models.backends.base import BackendType


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


class Resources(BaseModel):
    cpus: int
    memory_mib: int
    gpus: List[Gpu]
    spot: bool


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


class InstanceAvailability(Enum):
    UNKNOWN = "unknown"
    AVAILABLE = "available"
    NOT_AVAILABLE = "not_available"
    NO_QUOTA = "no_quota"


class InstanceOffer(BaseModel):
    instance: InstanceType
    region: str
    price: float


class InstanceOfferWithAvailability(InstanceOffer):
    availability: InstanceAvailability


class InstanceCandidate(InstanceOfferWithAvailability):
    backend: BackendType


class LaunchedGatewayInfo(BaseModel):
    instance_id: str
    ip_address: str
    region: str
