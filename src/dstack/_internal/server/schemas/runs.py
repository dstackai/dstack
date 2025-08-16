from datetime import datetime
from typing import Annotated, List, Literal, Optional
from uuid import UUID

import gpuhunt
from pydantic import Field

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.common import CoreModel
from dstack._internal.core.models.instances import InstanceAvailability
from dstack._internal.core.models.resources import Range
from dstack._internal.core.models.runs import ApplyRunPlanInput, RunSpec


class ListRunsRequest(CoreModel):
    project_name: Optional[str] = None
    repo_id: Optional[str] = None
    username: Optional[str] = None
    only_active: bool = False
    include_jobs: bool = Field(
        True,
        description=("Whether to include `jobs` in the response"),
    )
    job_submissions_limit: Optional[int] = Field(
        None,
        ge=0,
        description=(
            "Limit number of job submissions returned per job to avoid large responses."
            "Drops older job submissions. No effect with `include_jobs: false`"
        ),
    )
    prev_submitted_at: Optional[datetime] = None
    prev_run_id: Optional[UUID] = None
    limit: int = Field(100, ge=0, le=100)
    ascending: bool = False


class GetRunRequest(CoreModel):
    run_name: Optional[str] = None
    id: Optional[UUID] = None


class GetRunPlanRequest(CoreModel):
    run_spec: RunSpec
    max_offers: Optional[int] = Field(
        description="The maximum number of offers to return", ge=1, le=10000
    )


class SubmitRunRequest(CoreModel):
    run_spec: RunSpec


class ApplyRunPlanRequest(CoreModel):
    plan: ApplyRunPlanInput
    force: Annotated[
        bool,
        Field(
            description="Use `force: true` to apply even if the expected resource does not match."
        ),
    ]


class StopRunsRequest(CoreModel):
    runs_names: List[str]
    abort: Annotated[bool, Field(description="Do not wait for a graceful shutdown.")]


class DeleteRunsRequest(CoreModel):
    runs_names: List[str]


class BackendGpu(CoreModel):
    """GPU specification from a backend offer."""

    name: str
    memory_mib: int
    vendor: gpuhunt.AcceleratorVendor
    availability: InstanceAvailability
    spot: bool
    count: int
    price: float


class BackendGpus(CoreModel):
    """Backend GPU specifications."""

    backend_type: BackendType
    gpus: List[BackendGpu]
    regions: List[str]


class GetRunGpusRequest(CoreModel):
    """Request for getting run GPUs with optional grouping."""

    run_spec: RunSpec
    group_by: Optional[List[Literal["backend", "region", "count"]]] = Field(
        default=None,
        description="List of fields to group by. Valid values: 'backend', 'region', 'count'",
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


class RunGpusResponse(CoreModel):
    """Response containing GPU specifications."""

    gpus: List[GpuGroup] = Field(
        description="List of GPU specifications, grouped according to the group_by parameter"
    )
