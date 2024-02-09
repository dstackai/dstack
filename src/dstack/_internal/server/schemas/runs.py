from typing import List, Optional

from pydantic import BaseModel

from dstack._internal.core.models.instances import SSHKey
from dstack._internal.core.models.profiles import Profile
from dstack._internal.core.models.resources import ResourcesSpec
from dstack._internal.core.models.runs import Requirements, RunSpec


class ListRunsRequest(BaseModel):
    project_name: Optional[str]
    repo_id: Optional[str]


class GetRunRequest(BaseModel):
    run_name: str


class GetRunPlanRequest(BaseModel):
    run_spec: RunSpec


class GetOffersRequest(BaseModel):
    profile: Profile
    requirements: Requirements


class CreateInstanceRequest(BaseModel):
    pool_name: str
    profile: Profile
    requirements: Requirements
    ssh_key: SSHKey


class AddRemoteInstanceRequest(BaseModel):
    instance_name: Optional[str]
    host: str
    port: str
    resources: ResourcesSpec
    profile: Profile


class SubmitRunRequest(BaseModel):
    run_spec: RunSpec


class StopRunsRequest(BaseModel):
    runs_names: List[str]
    abort: bool


class DeleteRunsRequest(BaseModel):
    runs_names: List[str]
