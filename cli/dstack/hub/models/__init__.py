from typing import Dict, List, Optional, Union

from pydantic import BaseModel

from dstack.core.job import Job, JobHead
from dstack.core.repo import LocalRepoData, RepoAddress
from dstack.core.secret import Secret


class User(BaseModel):
    user_name: str
    token: Optional[str]
    global_role: str


class Project(BaseModel):
    name: str
    backend: str
    config: str


class Member(BaseModel):
    user_name: str
    project_role: str


class AWSConfig(BaseModel):
    region_name: str = ""
    region_name_title: str = ""
    s3_bucket_name: str = ""
    ec2_subnet_id: Optional[str] = ""


class AWSAuth(BaseModel):
    access_key: str = ""
    secret_key: str = ""


class GCPConfig(BaseModel):
    area: str = ""
    region: str = ""
    zone: str = ""
    bucket_name: Optional[str] = ""
    vpc: str = ""
    subnet: str = ""


class GCPAuth(BaseModel):
    credentials: str = ""


class AWSBackend(AWSConfig, AWSAuth):
    type: str = "aws"


class GCPBackend(GCPConfig, GCPAuth):
    type: str = "gcp"


class ProjectInfo(BaseModel):
    project_name: str
    backend: Union[AWSBackend, GCPBackend]
    members: List[Member] = []


class UserInfo(BaseModel):
    user_name: str
    global_role: str


class AddTagRun(BaseModel):
    repo_address: RepoAddress
    tag_name: str
    run_name: str
    run_jobs: List[Job]


class AddTagPath(BaseModel):
    repo_data: LocalRepoData
    tag_name: str
    local_dirs: List[str]


class StopRunners(BaseModel):
    repo_address: RepoAddress
    job_id: str
    abort: bool


class ReposUpdate(BaseModel):
    repo_address: RepoAddress
    last_run_at: int


class RunsList(BaseModel):
    repo_address: RepoAddress
    run_name: Optional[str]
    include_request_heads: Optional[bool]


class JobsGet(BaseModel):
    repo_address: RepoAddress
    job_id: str


class JobsList(BaseModel):
    repo_address: RepoAddress
    run_name: str


class ArtifactsList(BaseModel):
    repo_address: RepoAddress
    run_name: str


class SecretAddUpdate(BaseModel):
    repo_address: RepoAddress
    secret: Secret


class PollLogs(BaseModel):
    repo_address: RepoAddress
    job_heads: List[JobHead]
    start_time: int
    attached: bool


class LinkUpload(BaseModel):
    object_key: str


class ProjectDelete(BaseModel):
    projects: List[str] = []


class ProjectElementValue(BaseModel):
    name: Optional[str]
    created: Optional[str]
    region: Optional[str]
    value: Optional[str]
    label: Optional[str]
    vpc: Optional[str]
    subnet: Optional[str]


class ProjectElement(BaseModel):
    selected: Optional[str]
    values: List[ProjectElementValue] = []


class AWSProjectValues(BaseModel):
    type: str = "aws"
    region_name: Optional[ProjectElement]
    s3_bucket_name: Optional[ProjectElement]
    ec2_subnet_id: Optional[ProjectElement]


class GCPProjectValues(BaseModel):
    type: str = "gcp"
    area: Optional[ProjectElement]
    region: Optional[ProjectElement]
    zone: Optional[ProjectElement]
    bucket_name: Optional[ProjectElement]
    bucket_name: Optional[ProjectElement]
    vpc_subnet: Optional[ProjectElement]


class UserPatch(BaseModel):
    global_role: str


class AddMembers(BaseModel):
    members: List[Member] = []


class DeleteUsers(BaseModel):
    users: List[str] = []
