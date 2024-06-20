from datetime import datetime
from typing import List, Optional
from uuid import UUID

from dstack._internal.core.models.common import CoreModel
from dstack._internal.core.models.instances import SSHKey
from dstack._internal.core.models.profiles import Profile
from dstack._internal.core.models.runs import Requirements, RunSpec


class ListRunsRequest(CoreModel):
    project_name: Optional[str]
    repo_id: Optional[str]
    username: Optional[str]
    only_active: bool = False
    prev_submitted_at: Optional[datetime]
    prev_run_id: Optional[UUID]
    limit: int = 1000
    ascending: bool = False


class GetRunRequest(CoreModel):
    run_name: str


class GetRunPlanRequest(CoreModel):
    run_spec: RunSpec


class GetOffersRequest(CoreModel):
    profile: Profile
    requirements: Requirements


class CreateInstanceRequest(CoreModel):
    profile: Profile
    requirements: Requirements


class AddRemoteInstanceRequest(CoreModel):
    pool_name: Optional[str]
    instance_name: Optional[str]
    instance_network: Optional[str]
    region: Optional[str]
    host: str
    port: int
    ssh_user: str
    ssh_keys: List[SSHKey]


class SubmitRunRequest(CoreModel):
    run_spec: RunSpec


class StopRunsRequest(CoreModel):
    runs_names: List[str]
    abort: bool


class DeleteRunsRequest(CoreModel):
    runs_names: List[str]
