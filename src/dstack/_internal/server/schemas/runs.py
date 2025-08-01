from datetime import datetime
from typing import Annotated, List, Optional
from uuid import UUID

from pydantic import Field

from dstack._internal.core.models.common import CoreModel
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
