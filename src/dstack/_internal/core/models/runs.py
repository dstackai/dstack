from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional

from pydantic import UUID4, BaseModel, Field
from typing_extensions import Annotated

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.configurations import AnyRunConfiguration, RegistryAuth
from dstack._internal.core.models.instances import InstanceCandidate, InstanceType
from dstack._internal.core.models.profiles import Profile, SpotPolicy
from dstack._internal.core.models.repos import AnyRunRepoData
from dstack._internal.utils import common as common_utils


class AppSpec(BaseModel):
    port: int
    map_to_port: Optional[int]
    app_name: str
    url_path: Optional[str]
    url_query_params: Optional[Dict[str, str]]


class JobStatus(str, Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    PROVISIONING = "provisioning"
    RUNNING = "running"
    TERMINATING = "terminating"
    TERMINATED = "terminated"
    ABORTED = "aborted"
    FAILED = "failed"
    DONE = "done"

    @classmethod
    def finished_statuses(cls) -> List["JobStatus"]:
        return [cls.TERMINATED, cls.ABORTED, cls.FAILED, cls.DONE]

    def is_finished(self):
        return self in self.finished_statuses()


class RetryPolicy(BaseModel):
    retry: bool
    limit: Optional[int]


class JobErrorCode(str, Enum):
    # Set by the server
    FAILED_TO_START_DUE_TO_NO_CAPACITY = "failed_to_start_due_to_no_capacity"
    INTERRUPTED_BY_NO_CAPACITY = "interrupted_by_no_capacity"
    WAITING_RUNNER_LIMIT_EXCEEDED = "waiting_runner_limit_exceeded"
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
    max_price: Optional[float]
    spot: Optional[bool]

    def pretty_format(self):
        res = ""
        res += f"{self.cpus}xCPUs"
        res += f", {self.memory_mib}MB"
        if self.gpus:
            res += f", {self.gpus.count}x{self.gpus.name or 'GPU'}"
            if self.gpus.memory_mib:
                res += f" {self.gpus.memory_mib / 1024:g}GB"
        if self.spot is not None:
            res += f", {'spot' if self.spot else 'on-demand'}"
        if self.max_price is not None:
            res += f" under ${self.max_price:g} per hour"
        return res


class Gateway(BaseModel):
    gateway_name: Optional[str]
    service_port: int
    ssh_key: Optional[str]
    sock_path: Optional[str]
    hostname: Optional[str]
    public_port: int = 80
    secure: bool = False


class JobSpec(BaseModel):
    job_num: int
    job_name: str
    app_specs: Optional[List[AppSpec]]
    commands: List[str]
    env: Dict[str, str]
    gateway: Optional[Gateway]
    home_dir: Optional[str]
    image_name: str
    max_duration: Optional[int]
    registry_auth: Optional[RegistryAuth]
    requirements: Requirements
    retry_policy: RetryPolicy
    working_dir: str


class JobProvisioningData(BaseModel):
    backend: BackendType
    instance_type: InstanceType
    instance_id: str
    hostname: str
    region: str
    price: float
    username: str
    ssh_port: int  # could be different from 22 for some backends
    dockerized: bool  # True if JumpProxy is needed


class JobSubmission(BaseModel):
    id: UUID4
    submission_num: int
    submitted_at: datetime
    status: JobStatus
    error_code: Optional[JobErrorCode]
    job_provisioning_data: Optional[JobProvisioningData]

    @property
    def age(self):
        return common_utils.get_current_datetime() - self.submitted_at


class Job(BaseModel):
    job_spec: JobSpec
    job_submissions: List[JobSubmission]

    def is_retry_active(self):
        return self.job_spec.retry_policy.retry and (
            self.job_spec.retry_policy.limit is None
            or self.job_submissions[0].age < timedelta(seconds=self.job_spec.retry_policy.limit)
        )


class RunSpec(BaseModel):
    run_name: Optional[str]
    repo_id: str
    repo_data: Annotated[AnyRunRepoData, Field(discriminator="repo_type")]
    repo_code_hash: Optional[str]
    working_dir: str
    configuration_path: str
    configuration: Annotated[AnyRunConfiguration, Field(discriminator="type")]
    profile: Profile
    ssh_key_pub: str


class Run(BaseModel):
    id: UUID4
    project_name: str
    user: str
    submitted_at: datetime
    status: JobStatus
    run_spec: RunSpec
    jobs: List[Job]


class JobPlan(BaseModel):
    job_spec: JobSpec
    candidates: List[InstanceCandidate]


class RunPlan(BaseModel):
    project_name: str
    user: str
    run_spec: RunSpec
    job_plans: List[JobPlan]
