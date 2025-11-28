from typing import List, Literal, Optional

from pydantic import Field

from dstack._internal.core.models.common import CoreModel
from dstack._internal.core.models.gpus import GpuGroup
from dstack._internal.core.models.runs import RunSpec


class ListGpusRequest(CoreModel):
    """Request for listing GPUs with optional grouping."""

    run_spec: RunSpec
    group_by: Optional[List[Literal["backend", "region", "count"]]] = Field(
        default=None,
        description="List of fields to group by. Valid values: 'backend', 'region', 'count'. "
        "Note: 'region' can only be used together with 'backend'.",
    )


class ListGpusResponse(CoreModel):
    """Response containing GPU specifications."""

    gpus: List[GpuGroup] = Field(
        description="List of GPU specifications, grouped according to the group_by parameter"
    )
