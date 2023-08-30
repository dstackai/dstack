from datetime import datetime
from typing import List, Optional, Union

from pydantic import BaseModel, Field
from typing_extensions import Literal

from dstack._internal.core.job import Job
from dstack._internal.core.repo import RemoteRepoCredentials, RepoSpec
from dstack._internal.core.repo.head import RepoHead
from dstack._internal.core.run import RunHead
from dstack._internal.core.secret import Secret
from dstack._internal.hub.security.utils import GlobalRole, ProjectRole


class UserInfo(BaseModel):
    user_name: str
    global_role: GlobalRole


class UserInfoWithToken(UserInfo):
    token: Optional[str]


class Member(BaseModel):
    user_name: str
    project_role: ProjectRole


BackendType = Union[
    Literal["local"],
    Literal["aws"],
    Literal["azure"],
    Literal["gcp"],
    Literal["lambda"],
]


class LocalBackendConfig(BaseModel):
    type: Literal["local"] = "local"
    path: Optional[str]


class AWSBackendConfigPartial(BaseModel):
    type: Literal["aws"] = "aws"
    s3_bucket_name: Optional[str]
    regions: Optional[List[str]]
    ec2_subnet_id: Optional[str]


class AWSBackendConfig(BaseModel):
    type: Literal["aws"] = "aws"
    s3_bucket_name: str
    regions: List[str]
    ec2_subnet_id: Optional[str]


class AWSBackendDefaultCreds(BaseModel):
    type: Literal["default"] = "default"


class AWSBackendAccessKeyCreds(BaseModel):
    type: Literal["access_key"] = "access_key"
    access_key: str
    secret_key: str


class AWSBackendCreds(BaseModel):
    __root__: Union[AWSBackendAccessKeyCreds, AWSBackendDefaultCreds] = Field(
        ..., discriminator="type"
    )


class AWSBackendConfigWithCredsPartial(AWSBackendConfigPartial):
    credentials: Optional[AWSBackendCreds]


class AWSBackendConfigWithCreds(AWSBackendConfig):
    credentials: AWSBackendCreds


class GCPBackendConfigPartial(BaseModel):
    type: Literal["gcp"] = "gcp"
    bucket_name: Optional[str]
    regions: Optional[List[str]]
    vpc: Optional[str]
    subnet: Optional[str]


class GCPBackendConfig(BaseModel):
    type: Literal["gcp"] = "gcp"
    bucket_name: str
    regions: List[str]
    vpc: str
    subnet: str


class GCPBackendDefaultCreds(BaseModel):
    type: Literal["default"] = "default"


class GCPBackendServiceAccountCreds(BaseModel):
    type: Literal["service_account"] = "service_account"
    filename: str
    data: str


class GCPBackendCreds(BaseModel):
    __root__: Union[GCPBackendServiceAccountCreds, GCPBackendDefaultCreds] = Field(
        ..., discriminator="type"
    )


class GCPBackendConfigWithCredsPartial(GCPBackendConfigPartial):
    credentials: Optional[GCPBackendCreds]


class GCPBackendConfigWithCreds(GCPBackendConfig):
    credentials: GCPBackendCreds


class AzureBackendConfigPartial(BaseModel):
    type: Literal["azure"] = "azure"
    tenant_id: Optional[str]
    subscription_id: Optional[str]
    storage_account: Optional[str]
    locations: Optional[List[str]]


class AzureBackendClientCreds(BaseModel):
    type: Literal["client"] = "client"
    client_id: str
    client_secret: str


class AzureBackendDefaultCreds(BaseModel):
    type: Literal["default"] = "default"


class AzureBackendCreds(BaseModel):
    __root__: Union[AzureBackendClientCreds, AzureBackendDefaultCreds] = Field(
        ..., discriminator="type"
    )


class AzureBackendConfigWithCredsPartial(AzureBackendConfigPartial):
    credentials: Optional[AzureBackendCreds]


class AzureBackendConfig(BaseModel):
    type: Literal["azure"] = "azure"
    tenant_id: str
    subscription_id: str
    storage_account: str
    locations: List[str]


class AzureBackendConfigWithCreds(AzureBackendConfig):
    credentials: AzureBackendCreds


class AWSStorageBackendConfigWithCredsPartial(BaseModel):
    type: Literal["aws"] = "aws"
    bucket_name: Optional[str]
    credentials: Optional[AWSBackendAccessKeyCreds]


class AWSStorageBackendConfig(BaseModel):
    type: Literal["aws"] = "aws"
    bucket_name: str


class AWSStorageBackendConfigWithCreds(AWSStorageBackendConfig):
    credentials: AWSBackendAccessKeyCreds


class LambdaBackendConfigWithCredsPartial(BaseModel):
    type: Literal["lambda"] = "lambda"
    api_key: Optional[str]
    regions: Optional[List[str]]
    storage_backend: Optional[AWSStorageBackendConfigWithCredsPartial]


class LambdaBackendConfig(BaseModel):
    type: Literal["lambda"] = "lambda"
    regions: List[str]
    storage_backend: AWSStorageBackendConfig


class LambdaBackendConfigWithCreds(LambdaBackendConfig):
    api_key: str
    storage_backend: AWSStorageBackendConfigWithCreds


AnyBackendConfig = Union[
    LocalBackendConfig, AWSBackendConfig, GCPBackendConfig, AzureBackendConfig, LambdaBackendConfig
]
AnyBackendConfigWithCredsPartial = Union[
    LocalBackendConfig,
    AWSBackendConfigWithCredsPartial,
    GCPBackendConfigWithCredsPartial,
    AzureBackendConfigWithCredsPartial,
    LambdaBackendConfigWithCredsPartial,
]
AnyBackendConfigWithCreds = Union[
    LocalBackendConfig,
    AWSBackendConfigWithCreds,
    GCPBackendConfigWithCreds,
    AzureBackendConfigWithCreds,
    LambdaBackendConfigWithCreds,
]


class BackendInfo(BaseModel):
    __root__: AnyBackendConfig = Field(..., discriminator="type")


class BackendConfigWithCredsPartial(BaseModel):
    __root__: AnyBackendConfigWithCredsPartial = Field(..., discriminator="type")


class BackendConfigWithCreds(BaseModel):
    __root__: AnyBackendConfigWithCreds = Field(..., discriminator="type")


class BackendInfo(BaseModel):
    name: str
    config: AnyBackendConfig = Field(..., discriminator="type")


class BackendInfoWithCreds(BaseModel):
    name: str
    config: AnyBackendConfigWithCreds = Field(..., discriminator="type")


class BackendElementValue(BaseModel):
    value: str
    label: str


class BackendElement(BaseModel):
    selected: Optional[str]
    values: List[BackendElementValue] = []


class BackendMultiElement(BaseModel):
    selected: List[str] = []
    values: List[BackendElementValue] = []


class AWSBucketBackendElementValue(BaseModel):
    name: str
    created: str
    region: str


class AWSBucketBackendElement(BaseModel):
    selected: Optional[str]
    values: List[AWSBucketBackendElementValue] = []


class AWSBackendValues(BaseModel):
    type: Literal["aws"] = "aws"
    default_credentials: bool = False
    regions: Optional[BackendMultiElement]
    s3_bucket_name: Optional[AWSBucketBackendElement]
    ec2_subnet_id: Optional[BackendElement]


class GCPVPCSubnetBackendElementValue(BaseModel):
    label: Optional[str]
    vpc: Optional[str]
    subnet: Optional[str]


class GCPVPCSubnetBackendElement(BaseModel):
    selected: Optional[str]
    values: List[GCPVPCSubnetBackendElementValue] = []


class GCPBackendValues(BaseModel):
    type: Literal["gcp"] = "gcp"
    default_credentials: bool = False
    bucket_name: Optional[BackendElement]
    regions: Optional[BackendMultiElement]
    vpc_subnet: Optional[GCPVPCSubnetBackendElement]


class AzureBackendValues(BaseModel):
    type: Literal["azure"] = "azure"
    default_credentials: bool = False
    tenant_id: Optional[BackendElement]
    subscription_id: Optional[BackendElement]
    storage_account: Optional[BackendElement]
    locations: Optional[BackendMultiElement]


class AWSStorageBackendValues(BaseModel):
    type: Literal["aws"] = "aws"
    bucket_name: Optional[BackendElement]


class LambdaBackendValues(BaseModel):
    type: Literal["lambda"] = "lambda"
    storage_backend_type: BackendElement
    regions: Optional[BackendMultiElement]
    storage_backend_values: Optional[AWSStorageBackendValues]


class BackendValues(BaseModel):
    __root__: Union[
        None, AWSBackendValues, GCPBackendValues, AzureBackendValues, LambdaBackendValues
    ] = Field(..., discriminator="type")


class ProjectInfo(BaseModel):
    project_name: str
    backends: List[BackendInfo]
    members: List[Member] = []


class ProjectCreate(BaseModel):
    project_name: str
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


class RunRunners(BaseModel):
    job: Job


class StopRunners(BaseModel):
    repo_id: str
    job_id: str
    abort: bool
    terminate: Optional[bool] = False


class SaveRepoCredentials(BaseModel):
    repo_id: str
    repo_credentials: RemoteRepoCredentials


class RepoHeadGet(BaseModel):
    repo_id: str


class ReposUpdate(BaseModel):
    repo_spec: RepoSpec
    last_run_at: int


class ReposDelete(BaseModel):
    repo_ids: List[str]


class RunsGetPlan(BaseModel):
    jobs: List[Job]


class RunsCreate(BaseModel):
    repo_id: str
    run_name: Optional[str]


class RunsList(BaseModel):
    repo_id: str
    run_name: Optional[str]
    include_request_heads: Optional[bool]


class RunsStop(BaseModel):
    repo_id: str
    run_names: List[str]
    abort: bool
    terminate: Optional[bool] = False


class RunsDelete(BaseModel):
    repo_id: str
    run_names: List[str]


class RunInfo(BaseModel):
    project: str
    repo_id: str
    backend: Optional[str]
    run_head: RunHead
    repo: Optional[RepoHead]


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
    diagnose: bool = False


class StorageLink(BaseModel):
    backend: str
    object_key: str


class ProjectsDelete(BaseModel):
    projects: List[str] = []


class BackendsDelete(BaseModel):
    backends: List[str] = []


class UserPatch(BaseModel):
    global_role: GlobalRole


class AddMembers(BaseModel):
    members: List[Member] = []


class DeleteUsers(BaseModel):
    users: List[str] = []


class FileObject(BaseModel):
    object_key: str
