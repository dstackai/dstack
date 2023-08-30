from enum import Enum
from typing import List, Optional

from pydantic import BaseModel

from dstack._internal.core.runners import Resources


class InstanceType(BaseModel):
    instance_name: str
    resources: Resources
    available_regions: Optional[List[str]] = None


class LaunchedInstanceInfo(BaseModel):
    request_id: str
    location: Optional[str] = None


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
