from datetime import datetime
from typing import List, Optional, Union

from pydantic import BaseModel, Field
from typing_extensions import Literal

from dstack.core.job import Job
from dstack.core.repo import RemoteRepoCredentials, RepoSpec
from dstack.core.secret import Secret
from dstack.hub.security.utils import GlobalRole, ProjectRole


class UserInfo(BaseModel):
    user_name: str
    global_role: GlobalRole


class UserInfoWithToken(UserInfo):
    token: Optional[str]


class Project(BaseModel):
    name: str
    backend: str
    config: str


class Member(BaseModel):
    user_name: str
    project_role: ProjectRole


BackendType = Union[Literal["local"], Literal["aws"], Literal["gcp"], Literal["azure"]]


class LocalProjectConfig(BaseModel):
    type: Literal["local"] = "local"
    path: Optional[str]


class AWSProjectConfigPartial(BaseModel):
    type: Literal["aws"] = "aws"
    region_name: Optional[str]
    region_name_title: Optional[str]
    s3_bucket_name: Optional[str]
    ec2_subnet_id: Optional[str]


class AWSProjectConfig(BaseModel):
    type: Literal["aws"] = "aws"
    region_name: str
    region_name_title: Optional[str]
    s3_bucket_name: str
    ec2_subnet_id: Optional[str]


class AWSProjectCreds(BaseModel):
    access_key: str
    secret_key: str


class AWSProjectConfigWithCredsPartial(AWSProjectConfigPartial, AWSProjectCreds):
    pass


class AWSProjectConfigWithCreds(AWSProjectConfig, AWSProjectCreds):
    pass


class GCPProjectConfigPartial(BaseModel):
    type: Literal["gcp"] = "gcp"
    area: Optional[str]
    region: Optional[str]
    zone: Optional[str]
    bucket_name: Optional[str]
    vpc: Optional[str]
    subnet: Optional[str]


class GCPProjectConfig(BaseModel):
    type: Literal["gcp"] = "gcp"
    area: str
    region: str
    zone: str
    bucket_name: str
    vpc: str
    subnet: str


class GCPProjectCreds(BaseModel):
    credentials_filename: str
    credentials: str


class GCPProjectConfigWithCredsPartial(GCPProjectConfigPartial, GCPProjectCreds):
    pass


class GCPProjectConfigWithCreds(GCPProjectConfig, GCPProjectCreds):
    pass


class AzureProjectConfigPartial(BaseModel):
    type: Literal["azure"] = "azure"
    tenant_id: str
    subscription_id: Optional[str]
    location: Optional[str]
    storage_account: Optional[str]


class AzureProjectCreds(BaseModel):
    client_id: str
    client_secret: str


class AzureProjectConfigWithCredsPartial(AzureProjectConfigPartial, AzureProjectCreds):
    pass


class AzureProjectConfig(BaseModel):
    type: Literal["azure"] = "azure"
    tenant_id: str
    subscription_id: str
    location: str
    storage_account: str


class AzureProjectConfigWithCreds(AzureProjectConfig, AzureProjectCreds):
    pass


AnyProjectConfig = Union[
    LocalProjectConfig, AWSProjectConfig, GCPProjectConfig, AzureProjectConfig
]
AnyProjectConfigWithCredsPartial = Union[
    LocalProjectConfig,
    AWSProjectConfigWithCredsPartial,
    GCPProjectConfigWithCredsPartial,
    AzureProjectConfigWithCredsPartial,
]
AnyProjectConfigWithCreds = Union[
    LocalProjectConfig,
    AWSProjectConfigWithCreds,
    GCPProjectConfigWithCreds,
    AzureProjectConfigWithCreds,
]


class ProjectConfig(BaseModel):
    __root__: AnyProjectConfig = Field(..., discriminator="type")


class ProjectConfigWithCredsPartial(BaseModel):
    __root__: AnyProjectConfigWithCredsPartial = Field(..., discriminator="type")


class ProjectConfigWithCreds(BaseModel):
    __root__: AnyProjectConfigWithCreds = Field(..., discriminator="type")


class ProjectInfo(BaseModel):
    project_name: str
    backend: ProjectConfig
    members: List[Member] = []


class ProjectInfoWithCreds(BaseModel):
    project_name: str
    backend: ProjectConfigWithCreds
    members: List[Member] = []


class AddTagRun(BaseModel):
    repo_id: str
    tag_name: str
    run_name: str
    run_jobs: Optional[List[Job]]


class AddTagPath(BaseModel):
    repo_spec: RepoSpec
    tag_name: str
    local_dirs: List[str]


class StopRunners(BaseModel):
    repo_id: str
    job_id: str
    abort: bool


class SaveRepoCredentials(BaseModel):
    repo_id: str
    repo_credentials: RemoteRepoCredentials


class RepoHeadGet(BaseModel):
    repo_id: str


class ReposUpdate(BaseModel):
    repo_spec: RepoSpec
    last_run_at: int


class RunsList(BaseModel):
    repo_id: str
    run_name: Optional[str]
    include_request_heads: Optional[bool]


class RunsStop(BaseModel):
    repo_id: str
    run_names: List[str]
    abort: bool


class RunsDelete(BaseModel):
    repo_id: str
    run_names: List[str]


class JobHeadList(BaseModel):
    repo_id: str
    run_name: Optional[str]


class JobsGet(BaseModel):
    repo_id: str
    job_id: str


class JobsList(BaseModel):
    repo_id: str
    run_name: str


class ArtifactsList(BaseModel):
    repo_id: str
    run_name: str
    prefix: str
    recursive: bool


class SecretAddUpdate(BaseModel):
    repo_id: str
    secret: Secret


class PollLogs(BaseModel):
    repo_id: str
    run_name: str
    start_time: Optional[datetime]
    end_time: Optional[datetime]
    descending: bool = False
    prev_event_id: Optional[str]
    limit: int = Field(100, ge=0, le=1000)


class StorageLink(BaseModel):
    object_key: str


class ProjectDelete(BaseModel):
    projects: List[str] = []


class ProjectElementValue(BaseModel):
    value: str
    label: str


class ProjectElement(BaseModel):
    selected: Optional[str]
    values: List[ProjectElementValue] = []


class AWSBucketProjectElementValue(BaseModel):
    name: str
    created: str
    region: str


class AWSBucketProjectElement(BaseModel):
    selected: Optional[str]
    values: List[AWSBucketProjectElementValue] = []


class AWSProjectValues(BaseModel):
    type: Literal["aws"] = "aws"
    region_name: Optional[ProjectElement]
    s3_bucket_name: Optional[AWSBucketProjectElement]
    ec2_subnet_id: Optional[ProjectElement]


class GCPVPCSubnetProjectElementValue(BaseModel):
    label: Optional[str]
    vpc: Optional[str]
    subnet: Optional[str]


class GCPVPCSubnetProjectElement(BaseModel):
    selected: Optional[str]
    values: List[GCPVPCSubnetProjectElementValue] = []


class GCPProjectValues(BaseModel):
    type: Literal["gcp"] = "gcp"
    area: Optional[ProjectElement]
    region: Optional[ProjectElement]
    zone: Optional[ProjectElement]
    bucket_name: Optional[ProjectElement]
    vpc_subnet: Optional[GCPVPCSubnetProjectElement]


class AzureProjectValues(BaseModel):
    type: Literal["azure"] = "azure"
    tenant_id: Optional[ProjectElement]
    subscription_id: Optional[ProjectElement]
    location: Optional[ProjectElement]
    storage_account: Optional[ProjectElement]


class ProjectValues(BaseModel):
    __root__: Union[None, AWSProjectValues, GCPProjectValues, AzureProjectValues] = Field(
        ..., discriminator="type"
    )


class UserPatch(BaseModel):
    global_role: GlobalRole


class AddMembers(BaseModel):
    members: List[Member] = []


class DeleteUsers(BaseModel):
    users: List[str] = []


class FileObject(BaseModel):
    object_key: str
