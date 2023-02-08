from pydantic import BaseModel
from typing import Optional, List, Dict


class Hub(BaseModel):
    name: str
    backend: str


class UserInfo(BaseModel):
    user_name: str


class AppSpec(BaseModel):
    port_index: int
    app_name: str
    url_path: Optional[str] = None
    url_query_params: Optional[Dict[str, str]] = None


class AppHead(BaseModel):
    job_id: str
    app_name: str


class ArtifactSpec(BaseModel):
    artifact_path: str
    mount: bool


class ArtifactHead(BaseModel):
    job_id: str
    artifact_path: str


class Artifact(BaseModel):
    job_id: str
    name: str
    file: str
    filesize_in_bytes: int


class RepoAddress(BaseModel):
    repo_host_name: str
    repo_port: Optional[int]
    repo_user_name: str
    repo_name: str


class RepoData(RepoAddress):
    repo_branch: str
    repo_hash: str
    repo_diff: Optional[str]


class DepSpec(BaseModel):
    repo_address: RepoAddress
    run_name: str
    mount: bool


class Gpu(BaseModel):
    name: str
    memory_mib: int


class Resources(BaseModel):
    cpus: int
    memory_mib: int
    gpus: Optional[List[Gpu]]
    interruptible: bool
    local: bool


class InstanceType(BaseModel):
    instance_name: str
    resources: Resources


class TagHead(BaseModel):
    repo_address: RepoAddress
    tag_name: str
    run_name: str
    workflow_name: Optional[str]
    provider_name: Optional[str]
    local_repo_user_name: Optional[str]
    created_at: int
    artifact_heads: Optional[List[ArtifactHead]]


class GpusRequirements(BaseModel):
    count: Optional[int]
    memory_mib: Optional[int]
    name: Optional[str]


class Requirements(BaseModel):
    cpus: Optional[int]
    memory_mib: Optional[int]
    gpus: Optional[GpusRequirements]
    shm_size_mib: Optional[int]
    interruptible: Optional[bool]
    local: Optional[bool]


class JobRefId(BaseModel):
    job_id: str


class JobHead(JobRefId):
    repo_address: RepoAddress
    run_name: str
    workflow_name: Optional[str]
    provider_name: str
    local_repo_user_name: Optional[str]
    status: str
    submitted_at: int
    artifact_paths: Optional[List[str]]
    tag_name: Optional[str]
    app_names: Optional[List[str]]


class Job(JobHead):
    job_id: Optional[str]
    repo_data: RepoData
    run_name: str
    workflow_name: Optional[str]
    provider_name: str
    local_repo_user_name: Optional[str]
    local_repo_user_email: Optional[str]
    status: str
    submitted_at: int
    image_name: str
    commands: Optional[List[str]]
    env: Optional[Dict[str, str]]
    working_dir: Optional[str]
    artifact_specs: Optional[List[ArtifactSpec]]
    port_count: Optional[int]
    ports: Optional[List[int]]
    host_name: Optional[str]
    requirements: Optional[Requirements]
    dep_specs: Optional[List[DepSpec]]
    master_job: Optional[JobRefId]
    app_specs: Optional[List[AppSpec]]
    runner_id: Optional[str]
    request_id: Optional[str]
    tag_name: Optional[str]


class JobSpec(JobRefId):
    image_name: str
    commands: Optional[List[str]] = None
    env: Optional[Dict[str, str]] = None
    working_dir: Optional[str] = None
    artifact_specs: Optional[List[ArtifactSpec]] = None
    port_count: Optional[int] = None
    requirements: Optional[Requirements] = None
    master_job: Optional[JobRefId] = None
    app_specs: Optional[List[AppSpec]] = None


class LogEvent(BaseModel):
    event_id: str
    timestamp: int
    job_id: Optional[str]
    log_message: str
    log_source: str


class RepoHead(RepoAddress):
    last_run_at: Optional[int]
    tags_count: int


class RepoCredentials(BaseModel):
    protocol: str
    private_key: Optional[str]
    oauth_token: Optional[str]


class LocalRepoData(RepoData):
    protocol: str
    identity_file: Optional[str]
    oauth_token: Optional[str]
    local_repo_user_name: Optional[str]
    local_repo_user_email: Optional[str]


class RequestHead(BaseModel):
    job_id: str
    status: str
    message: Optional[str]


class RunHead(BaseModel):
    repo_address: RepoAddress
    run_name: str
    workflow_name: Optional[str]
    provider_name: str
    local_repo_user_name: Optional[str]
    artifact_heads: Optional[List[ArtifactHead]]
    status: str
    submitted_at: int
    tag_name: Optional[str]
    app_heads: Optional[List[AppHead]]
    request_heads: Optional[List[RequestHead]]


class Runner(BaseModel):
    runner_id: str
    request_id: Optional[str]
    resources: Resources
    job: Job


class Secret(BaseModel):
    secret_name: str
    secret_value: str
