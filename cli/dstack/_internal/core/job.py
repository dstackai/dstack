import json
from abc import abstractmethod
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field, root_validator
from typing_extensions import Annotated

from dstack._internal.core.app import AppSpec
from dstack._internal.core.artifact import ArtifactSpec
from dstack._internal.core.build import BuildPolicy
from dstack._internal.core.cache import CacheSpec
from dstack._internal.core.dependents import DepSpec
from dstack._internal.core.repo import (
    LocalRepo,
    LocalRepoData,
    RemoteRepo,
    RemoteRepoData,
    Repo,
    RepoData,
    RepoRef,
)
from dstack._internal.utils.common import get_milliseconds_since_epoch


class Gateway(BaseModel):
    gateway_name: Optional[str]
    hostname: Optional[str]
    service_port: int
    public_port: int = 80
    secure: bool = False
    ssh_key: Optional[str]
    sock_path: Optional[str]


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


class JobRef(BaseModel):
    @abstractmethod
    def get_id(self) -> Optional[str]:
        pass

    @abstractmethod
    def set_id(self, job_id: Optional[str]):
        pass


class JobRefId(JobRef):
    job_id: str

    def get_id(self) -> Optional[str]:
        return self.job_id

    def set_id(self, job_id: Optional[str]):
        self.job_id = job_id


class ConfigurationType(str, Enum):
    DEV_ENVIRONMENT = "dev-environment"
    TASK = "task"
    SERVICE = "service"


class JobStatus(str, Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    DOWNLOADING = "downloading"
    BUILDING = "building"
    RUNNING = "running"
    UPLOADING = "uploading"
    STOPPING = "stopping"
    STOPPED = "stopped"
    RESTARTING = "restarting"
    TERMINATING = "terminating"
    TERMINATED = "terminated"
    ABORTING = "aborting"
    ABORTED = "aborted"
    FAILED = "failed"
    DONE = "done"

    def is_finished(self):
        return self in [self.STOPPED, self.TERMINATED, self.ABORTED, self.FAILED, self.DONE]

    def is_unfinished(self):
        return not self.is_finished()

    def is_active(self):
        return self.is_unfinished() or self == self.STOPPED


class SpotPolicy(str, Enum):
    SPOT = "spot"
    ONDEMAND = "on-demand"
    AUTO = "auto"


class RetryPolicy(BaseModel):
    retry: bool
    limit: Optional[int]


class TerminationPolicy(str, Enum):
    STOP = "stop"
    TERMINATE = "terminate"


class JobErrorCode(str, Enum):
    # Set by CLI
    NO_INSTANCE_MATCHING_REQUIREMENTS = "no_instance_matching_requirements"
    FAILED_TO_START_DUE_TO_NO_CAPACITY = "failed_to_start_due_to_no_capacity"
    INTERRUPTED_BY_NO_CAPACITY = "interrupted_by_no_capacity"
    INSTANCE_TERMINATED = "instance_terminated"
    # Set by runner
    CONTAINER_EXITED_WITH_ERROR = "container_exited_with_error"
    BUILD_NOT_FOUND = "build_not_found"
    PORTS_BINDING_FAILED = "ports_binding_failed"

    def pretty_repr(self) -> str:
        return " ".join(self.value.split("_")).capitalize()


class JobHead(JobRef):
    job_id: str
    repo_ref: RepoRef
    hub_user_name: str = ""
    run_name: str
    workflow_name: Optional[str] = ""  # deprecated
    provider_name: Optional[str] = ""  # deprecated
    configuration_path: Optional[str]
    status: JobStatus
    error_code: Optional[JobErrorCode]
    container_exit_code: Optional[int]
    submitted_at: int
    artifact_paths: Optional[List[str]]
    tag_name: Optional[str]
    app_names: Optional[List[str]]
    instance_type: Optional[str]
    instance_spot_type: Optional[str]
    price: Optional[float]

    def get_id(self) -> Optional[str]:
        return self.job_id

    def set_id(self, job_id: Optional[str]):
        self.job_id = job_id


class RegistryAuth(BaseModel):
    username: Optional[str] = None
    password: Optional[str] = None


class Job(JobHead):
    app_names: Optional[List[str]]
    app_specs: Optional[List[AppSpec]]
    artifact_paths: Optional[List[str]]
    artifact_specs: Optional[List[ArtifactSpec]]
    backends: Optional[List[str]]
    build_commands: Optional[List[str]]
    build_policy: BuildPolicy = BuildPolicy.USE_BUILD
    cache_specs: List[CacheSpec]
    commands: Optional[List[str]]
    configuration_path: Optional[str]
    configuration_type: Optional[ConfigurationType]
    container_exit_code: Optional[int]
    created_at: int
    dep_specs: Optional[List[DepSpec]]
    entrypoint: Optional[List[str]]
    env: Optional[Dict[str, str]]
    error_code: Optional[JobErrorCode]
    gateway: Optional[Gateway]
    home_dir: Optional[str]
    host_name: Optional[str]
    hub_user_name: str = ""
    image_name: str
    instance_name: Optional[str]
    instance_spot_type: Optional[str]
    instance_type: Optional[str]
    job_id: str
    # TODO: Rename to `region_name`
    location: Optional[str]
    master_job: Optional[str]  # not implemented
    max_duration: Optional[int]
    price: Optional[float]
    provider_name: Optional[str] = ""  # deprecated
    registry_auth: Optional[RegistryAuth]
    repo_code_filename: Optional[str]
    repo_data: Annotated[
        Union[RepoData, RemoteRepoData, LocalRepoData], Field(discriminator="repo_type")
    ]
    repo_ref: RepoRef
    request_id: Optional[str]
    requirements: Optional[Requirements]
    retry_policy: Optional[RetryPolicy]
    run_name: str
    runner_id: Optional[str]
    setup: Optional[List[str]]
    spot_policy: Optional[SpotPolicy]
    ssh_key_pub: Optional[str]
    status: JobStatus
    submission_num: int = 1
    submitted_at: int
    tag_name: Optional[str]
    termination_policy: Optional[TerminationPolicy]
    workflow_name: Optional[str] = ""  # deprecated
    working_dir: Optional[str]

    @root_validator(pre=True)
    def preprocess_data(cls, data):
        # TODO Ugly style
        data["artifact_paths"] = (
            [check_dict(a, "artifact_path") for a in data.get("artifact_specs")]
            if data.get("artifact_specs")
            else None
        )
        data["app_names"] = (
            [check_dict(a, "app_name") for a in data.get("app_specs")]
            if data.get("app_specs")
            else None
        )
        return data

    def get_instance_spot_type(self) -> str:
        if self.requirements and self.requirements.spot:
            return "spot"
        return "on-demand"

    def serialize(self) -> dict:
        # hack to convert enum to string
        return json.loads(self.json(exclude_none=True))

    @staticmethod
    def unserialize(job_data: dict) -> "Job":
        return Job.parse_obj(job_data)

    @property
    def repo(self) -> Repo:
        if isinstance(self.repo_data, RemoteRepoData):
            return RemoteRepo(repo_ref=self.repo_ref, repo_data=self.repo_data)
        elif isinstance(self.repo_data, LocalRepoData):
            return LocalRepo(repo_ref=self.repo_ref, repo_data=self.repo_data)

    def retry_active(self, curr_time: Optional[int] = None) -> bool:
        if curr_time is None:
            curr_time = get_milliseconds_since_epoch()
        return (
            self.retry_policy is not None
            and self.retry_policy.retry
            and curr_time - self.created_at < self.retry_policy.limit * 1000
        )


def check_dict(element: Any, field: str):
    if type(element) == dict:
        return element.get(field)
    if hasattr(element, field):
        return getattr(element, field)
    return None
