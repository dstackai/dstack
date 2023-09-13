from datetime import datetime
from enum import Enum
from typing import Annotated, Dict, List, Optional

from pydantic import UUID4, BaseModel, Field

from dstack._internal.core.models.configurations import (
    AnyRunConfiguration,
    RegistryAuth,
    RunConfiguration,
)
from dstack._internal.core.models.instances import InstanceCandidate, InstanceType
from dstack._internal.core.models.profiles import Profile, SpotPolicy
from dstack._internal.core.models.repos import AnyRunRepoData


class AppSpec(BaseModel):
    port: int
    map_to_port: Optional[int]
    app_name: str
    url_path: Optional[str]
    url_query_params: Optional[Dict[str, str]]


class JobStatus(str, Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    RUNNING = "running"
    TERMINATING = "terminating"
    TERMINATED = "terminated"
    ABORTED = "aborted"
    FAILED = "failed"
    DONE = "done"

    def is_finished(self):
        return self in [self.TERMINATED, self.ABORTED, self.FAILED, self.DONE]

    def is_unfinished(self):
        return not self.is_finished()


class RetryPolicy(BaseModel):
    retry: bool
    limit: Optional[int]


class JobErrorCode(str, Enum):
    # Set by the server
    NO_INSTANCE_MATCHING_REQUIREMENTS = "no_instance_matching_requirements"
    FAILED_TO_START_DUE_TO_NO_CAPACITY = "failed_to_start_due_to_no_capacity"
    INTERRUPTED_BY_NO_CAPACITY = "interrupted_by_no_capacity"
    INSTANCE_TERMINATED = "instance_terminated"
    # Set by the runner
    CONTAINER_EXITED_WITH_ERROR = "container_exited_with_error"
    PORTS_BINDING_FAILED = "ports_binding_failed"

    def pretty_repr(self) -> str:
        return " ".join(self.value.split("_")).capitalize()


class GpusRequirements(BaseModel):
    count: Optional[int]
    memory_mib: Optional[int]
    name: Optional[str]


class Requirements(BaseModel):
    cpus: Optional[int]
    memory_mib: Optional[int]
    gpus: Optional[GpusRequirements]
    shm_size_mib: Optional[int]
    spot: Optional[bool]
    local: Optional[bool]
    max_price: Optional[float]

    def pretty_format(self):
        res = ""
        res += f"{self.cpus}xCPUs"
        res += f", {self.memory_mib}MB"
        if self.gpus:
            res += f", {self.gpus.count}x{self.gpus.name or 'GPU'}"
            if self.gpus.memory_mib:
                res += f" {self.gpus.memory_mib / 1024:g}GB"
        if self.max_price is not None:
            res += f" under ${self.max_price:g} per hour"
        return res


class Gateway(BaseModel):
    gateway_name: Optional[str]
    hostname: Optional[str]
    service_port: int
    public_port: int = 80
    secure: bool = False
    ssh_key: Optional[str]
    sock_path: Optional[str]


class JobSpec(BaseModel):
    app_names: List[str]
    app_specs: Optional[List[AppSpec]]
    commands: List[str]
    entrypoint: Optional[List[str]]
    env: Dict[str, str]
    gateway: Optional[Gateway]
    home_dir: Optional[str]
    image_name: str
    max_duration: Optional[int]
    price: Optional[float]
    registry_auth: Optional[RegistryAuth]
    requirements: Requirements
    retry_policy: RetryPolicy
    spot_policy: SpotPolicy
    working_dir: str


class JobSubmission(BaseModel):
    id: UUID4
    submission_num: int
    created_at: int
    status: JobStatus
    error_code: Optional[JobErrorCode]
    container_exit_code: Optional[int]
    hostname: str
    instance_type: InstanceType
    instance_id: str
    spot_request_id: Optional[str]
    location: str


class Job(BaseModel):
    job_num: int
    job_name: str
    job_spec: JobSpec
    job_submissions: List[JobSubmission]


class Run(BaseModel):
    id: UUID4
    run_name: str
    project_id: str
    repo_id: str
    repo_data: Annotated[AnyRunRepoData, Field(discriminator="repo_type")]
    repo_code_hash: Optional[str]
    user: str
    created_at: datetime
    configuration_path: str
    configuration: Annotated[AnyRunConfiguration, Field(discriminator="type")]
    profile: Profile
    ssh_key_pub: str
    code_hash: Optional[str]
    jobs: List[Job]


class JobPlan(BaseModel):
    job_num: int
    job_spec: JobSpec
    candidates: List[InstanceCandidate]


class RunPlan(BaseModel):
    project_id: str
    user: str
    repo_id: str
    repo_data: Annotated[AnyRunRepoData, Field(discriminator="repo_type")]
    repo_code_hash: Optional[str]
    configuration_path: str
    configuration: Annotated[AnyRunConfiguration, Field(discriminator="type")]
    profile: Profile
    ssh_key_pub: str
    code_hash: Optional[str]
    job_plans: List[JobPlan]
