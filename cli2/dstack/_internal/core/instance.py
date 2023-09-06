from enum import Enum
from typing import List, Optional

from pydantic import BaseModel


class Gpu(BaseModel):
    name: str
    memory_mib: int


class Resources(BaseModel):
    cpus: int
    memory_mib: int
    gpus: List[Gpu]
    spot: bool
    local: bool


class InstanceType(BaseModel):
    name: str
    resources: Resources
    available_regions: Optional[List[str]] = None


class LaunchedInstanceInfo(BaseModel):
    request_id: str
    location: str


class InstanceAvailability(Enum):
    UNKNOWN = "unknown"
    AVAILABLE = "available"
    NOT_AVAILABLE = "not_available"
    NO_QUOTA = "no_quota"


class InstancePricing(BaseModel):
    instance: InstanceType
    region: str
    price: float


class InstanceOffer(InstancePricing):
    availability: InstanceAvailability


class InstanceCandidate(InstanceOffer):
    backend: str
