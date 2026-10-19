from typing import Annotated, List, Literal, Optional

from pydantic import Field

from dstack._internal.core.models.common import CoreModel
from dstack._internal.core.models.gpus import CpuGroup, GpuGroup
from dstack._internal.core.models.runs import RunSpec


class ListGpusRequest(CoreModel):
    """Request for listing GPUs with optional grouping."""

    run_spec: RunSpec
    group_by: Optional[List[Literal["backend", "region", "count"]]] = Field(
        default=None,
        description="List of fields to group by. Valid values: 'backend', 'region', 'count'. "
        "Note: 'region' can only be used together with 'backend'.",
    )
    reverse: Annotated[
        bool,
        Field(
            description="Sort groups by descending whole-offer price range, "
            "keeping available groups first."
        ),
    ] = False
    full_offers: Annotated[
        bool, Field(description="Don't adjust backend offers by requirements")
    ] = False
    unallocated_resources: Annotated[
        bool,
        Field(description="Subtract allocated resources to return only unallocated resources"),
    ] = False


class ListGpusResponse(CoreModel):
    """Response containing GPU specifications."""

    gpus: List[GpuGroup] = Field(
        description="List of GPU specifications, grouped according to the group_by parameter"
    )
    cpus: Optional[List[CpuGroup]] = Field(
        default=None,
        description="CPU groups, returned only when the GPU count is constrained to zero",
    )
