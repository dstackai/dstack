from typing import List, Optional

from pydantic import BaseModel

from dstack._internal.core.models.profiles import Profile
from dstack._internal.core.models.runs import RunSpec


class ListRunsRequest(BaseModel):
    project_name: Optional[str]
    repo_id: Optional[str]


class GetRunRequest(BaseModel):
    run_name: str


class GetRunPlanRequest(BaseModel):
    run_spec: RunSpec


class GetOffersRequest(BaseModel):
    profile: Profile


class CreateInstanceRequest(BaseModel):
    pool_name: str
    profile: Profile


class AddInstanceRequest(BaseModel):
    pool_name: str
    instance_name: Optional[str]
    host: str
    port: str
    # TODO: define runner spec (gpu, cpu, etc)


class SubmitRunRequest(BaseModel):
    run_spec: RunSpec


class StopRunsRequest(BaseModel):
    runs_names: List[str]
    abort: bool


class DeleteRunsRequest(BaseModel):
    runs_names: List[str]
