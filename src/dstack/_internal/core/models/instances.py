from enum import Enum
from typing import List, Optional

from pydantic import BaseModel

from dstack._internal.core.models.backends.base import BackendType


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
    spot_request_id: Optional[str]
    region: str


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


class InstanceCandidate(InstanceOffer):
    backend: BackendType
