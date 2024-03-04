from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Sequence

from pydantic import UUID4, BaseModel, Field
from typing_extensions import Annotated

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.configurations import AnyRunConfiguration, RegistryAuth
from dstack._internal.core.models.instances import (
    InstanceOfferWithAvailability,
    InstanceType,
    SSHConnectionParams,
)
from dstack._internal.core.models.profiles import Profile, SpotPolicy
from dstack._internal.core.models.repos import AnyRunRepoData
from dstack._internal.core.models.resources import ResourcesSpec
from dstack._internal.utils import common as common_utils
from dstack._internal.utils.common import pretty_resources


class AppSpec(BaseModel):
    port: int
    map_to_port: Optional[int]
    app_name: str
    url_path: Optional[str] = None
    url_query_params: Optional[Dict[str, str]] = None


class JobStatus(str, Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    PROVISIONING = "provisioning"
    PULLING = "pulling"
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
    TERMINATED_BY_USER = "terminated_by_user"
    GATEWAY_ERROR = "gateway_error"
    # Set by the runner
    CONTAINER_EXITED_WITH_ERROR = "container_exited_with_error"
    PORTS_BINDING_FAILED = "ports_binding_failed"

    def pretty_repr(self) -> str:
        return " ".join(self.value.split("_")).capitalize()


class Requirements(BaseModel):
    # TODO: Make requirements' fields required
    resources: ResourcesSpec
    max_price: Optional[float]
    spot: Optional[bool]

    def pretty_format(self, resources_only: bool = False):
        resources = dict(cpus=self.resources.cpu, memory=self.resources.memory)
        if self.resources.gpu:
            gpu = self.resources.gpu
            resources.update(
                gpu_name=",".join(gpu.name) if gpu.name else None,
                gpu_count=gpu.count,
                gpu_memory=gpu.memory,
                total_gpu_memory=gpu.total_memory,
                compute_capability=gpu.compute_capability,
            )
        if self.resources.disk:
            resources.update(disk_size=self.resources.disk.size)
        res = pretty_resources(**resources)
        if not resources_only:
            if self.spot is not None:
                res += f", {'spot' if self.spot else 'on-demand'}"
            if self.max_price is not None:
                res += f" under ${self.max_price:g} per hour"
        return res


class Gateway(BaseModel):
    gateway_name: Optional[str]
    service_port: int
    hostname: Optional[str]
    public_port: int = 80
    secure: bool = False

    auth: bool = True
    options: dict = {}


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
    pool_name: Optional[str]  # TODO: remove pool_name from JobSpec


class JobProvisioningData(BaseModel):
    backend: BackendType
    instance_type: InstanceType
    instance_id: str
    hostname: str
    region: str
    price: float
    username: str
    ssh_port: int  # could be different from 22 for some backends
    dockerized: bool  # True if backend starts shim
    ssh_proxy: Optional[SSHConnectionParams]
    backend_data: Optional[str]  # backend-specific data in json


class JobSubmission(BaseModel):
    id: UUID4
    submission_num: int
    submitted_at: datetime
    finished_at: Optional[datetime]
    status: JobStatus
    error_code: Optional[JobErrorCode]
    job_provisioning_data: Optional[JobProvisioningData]

    @property
    def age(self) -> timedelta:
        return common_utils.get_current_datetime() - self.submitted_at

    @property
    def duration(self) -> timedelta:
        end_time = common_utils.get_current_datetime()
        if self.finished_at is not None:
            end_time = self.finished_at
        return end_time - self.submitted_at


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


class ServiceModelInfo(BaseModel):
    name: str
    base_url: str
    type: str


class ServiceInfo(BaseModel):
    url: str
    model: Optional[ServiceModelInfo] = None


class Run(BaseModel):
    id: UUID4
    project_name: str
    user: str
    submitted_at: datetime
    status: JobStatus
    run_spec: RunSpec
    jobs: List[Job]
    latest_job_submission: Optional[JobSubmission]
    cost: float = 0
    service: Optional[ServiceInfo] = None


class JobPlan(BaseModel):
    job_spec: JobSpec
    offers: List[InstanceOfferWithAvailability]
    total_offers: int
    max_price: Optional[float]


class RunPlan(BaseModel):
    project_name: str
    user: str
    run_spec: RunSpec
    job_plans: List[JobPlan]


class PoolInstanceOffers(BaseModel):
    pool_name: str
    instances: List[InstanceOfferWithAvailability]


class InstanceStatus(str, Enum):
    PENDING = "pending"
    CREATING = "creating"  # TODO: Backward compatibility, will be removed in 0.17
    STARTING = "starting"  # TODO: Backward compatibility, will be removed in 0.17
    READY = "ready"  # TODO: Backward compatibility, will be removed in 0.17
    PROVISIONING = "provisioning"
    IDLE = "idle"
    BUSY = "busy"
    TERMINATING = "terminating"
    TERMINATED = "terminated"

    @property
    def finished_statuses(cls) -> Sequence["InstanceStatus"]:  # TODO: remove in 0.17
        return [cls.TERMINATED]

    def is_finished(self):  # TODO: remove in 0.17
        return self in self.finished_statuses

    def is_started(self):  # TODO: remove in 0.17
        return not self.is_finished()

    def is_available(self) -> bool:
        return self in (
            self.READY,  # TODO: Backward compatibility, will be removed in 0.17
            self.IDLE,
            self.BUSY,
        )


def get_policy_map(spot_policy: Optional[SpotPolicy], default: SpotPolicy) -> Optional[bool]:
    """Map profile.spot_policy[SpotPolicy|None] to requirements.spot[bool|None]
    - SpotPolicy.AUTO by default for `dstack run`
    - SpotPolicy.ONDEMAND by default for `dstack pool add`
    """
    if spot_policy is None:
        spot_policy = default
    policy_map = {
        SpotPolicy.AUTO: None,
        SpotPolicy.SPOT: True,
        SpotPolicy.ONDEMAND: False,
    }
    return policy_map[spot_policy]
