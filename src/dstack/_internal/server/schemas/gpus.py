from typing import List, Literal, Optional

import gpuhunt
from pydantic import Field

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.common import CoreModel
from dstack._internal.core.models.instances import InstanceAvailability
from dstack._internal.core.models.resources import Range
from dstack._internal.core.models.runs import RunSpec


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


class ListGpusRequest(CoreModel):
    """Request for listing GPUs with optional grouping."""

    run_spec: RunSpec
    group_by: Optional[List[Literal["backend", "region", "count"]]] = Field(
        default=None,
        description="List of fields to group by. Valid values: 'backend', 'region', 'count'. "
        "Note: 'region' can only be used together with 'backend'.",
    )


class GpuGroup(CoreModel):
    """GPU group that can handle all grouping scenarios."""

    name: str
    memory_mib: int
    vendor: gpuhunt.AcceleratorVendor
    availability: List[InstanceAvailability]
    spot: List[Literal["spot", "on-demand"]]
    count: Range[int]
    price: Range[float]
    backends: Optional[List[BackendType]] = None
    backend: Optional[BackendType] = None
    regions: Optional[List[str]] = None
    region: Optional[str] = None


class ListGpusResponse(CoreModel):
    """Response containing GPU specifications."""

    gpus: List[GpuGroup] = Field(
        description="List of GPU specifications, grouped according to the group_by parameter"
    )
