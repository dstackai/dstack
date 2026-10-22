from typing import List, Literal, Optional

import gpuhunt

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.common import CoreModel
from dstack._internal.core.models.instances import InstanceAvailability
from dstack._internal.core.models.resources import Range


class BackendGpu(CoreModel):
    """GPU specification from a backend offer."""

    name: str
    memory_mib: int
    vendor: gpuhunt.AcceleratorVendor
    availability: InstanceAvailability
    spot: bool
    count: int
    price: float
    region: str


class BackendGpus(CoreModel):
    """Backend GPU specifications."""

    backend_type: BackendType
    gpus: List[BackendGpu]
    regions: List[str]


class GpuGroup(CoreModel):
    """GPU group that can handle all grouping scenarios."""

    name: str
    memory_mib: int
    vendor: gpuhunt.AcceleratorVendor
    availability: List[InstanceAvailability]
    spot: List[Literal["spot", "on-demand"]]
    count: Range[int]
    price: Range[float]
    offer_price: Optional[Range[float]] = None
    """Hourly price range for whole offers; `price` remains per GPU for compatibility."""
    backends: Optional[List[BackendType]] = None
    backend: Optional[BackendType] = None
    regions: Optional[List[str]] = None
    region: Optional[str] = None


class CpuGroup(CoreModel):
    """CPU-only offers grouped by resources and optional backend, region, or count."""

    cpu_arch: List[gpuhunt.CPUArchitecture]
    count: Range[int]
    memory_mib: Range[int]
    price: Range[float]
    """Hourly price range for whole offers."""
    availability: List[InstanceAvailability]
    spot: List[Literal["spot", "on-demand"]]
    backends: Optional[List[BackendType]] = None
    backend: Optional[BackendType] = None
    regions: Optional[List[str]] = None
    region: Optional[str] = None
