from base64 import b64decode
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import field_validator

from dstack._internal.core.models.common import CoreModel, NetworkMode
from dstack._internal.core.models.repos.remote import RemoteRepoCreds
from dstack._internal.core.models.runs import (
    ClusterInfo,
    ImagePullProgress,
    JobSpec,
    JobStatus,
    JobSubmission,
    Run,
    RunSpec,
)
from dstack._internal.core.models.volumes import InstanceMountPoint, VolumeMountPoint
from dstack._internal.server.schemas.health.dcgm import DCGMHealthResponse


class JobStateEvent(CoreModel):
    timestamp: int
    state: JobStatus
    termination_reason: Optional[str] = None
    termination_message: Optional[str] = None
    exit_status: Optional[int] = None


class LogEvent(CoreModel):
    timestamp: int
    """`timestamp` is stored in milliseconds."""
    message: bytes

    @field_validator("message", mode="before")
    @classmethod
    def decode_message(cls, v: Union[str, bytes]) -> bytes:
        if isinstance(v, str):
            return b64decode(v)
        return v


class PullResponse(CoreModel):
    job_states: List[JobStateEvent]
    job_logs: List[LogEvent]
    runner_logs: List[LogEvent]
    last_updated: int
    no_connections_secs: Optional[int] = None
    """`no_connections_secs` is optional for compatibility with old runners."""


class JobInfoResponse(CoreModel):
    working_dir: str
    username: str


# What the runner is actually sent. This used to be spelled as `Field(include=...)` per field, but
# pydantic v2 removed `include` from `Field` — it is silently ignored there, which would have sent
# the runner every field of `Run`, `JobSpec` and `JobSubmission` instead of these subsets. It lives
# on the model rather than at the call site so that a new caller cannot bypass it.
#
# A name the target model does not declare is ignored: `entrypoint` and `gateway` are listed for
# `job_spec` but `JobSpec` has neither.
_SUBMIT_BODY_INCLUDE: Dict[str, Any] = {
    "run": {
        "id": True,
        "run_spec": {
            "run_name",
            "repo_id",
            "repo_data",
            "configuration",
            "configuration_path",
        },
    },
    "job_spec": {
        "replica_num",
        "job_num",
        "jobs_per_replica",
        "user",
        "commands",
        "entrypoint",
        "env",
        "gateway",
        "single_branch",
        "max_duration",
        "ssh_key",
        "working_dir",
        "repo_dir",
        "repo_data",
        "repo_exists_action",
        "file_archives",
    },
    "job_submission": {"id"},
    "cluster_info": True,
    "secrets": True,
    "repo_credentials": True,
    "log_quota_hour": True,
    "run_spec": {
        "run_name",
        "repo_id",
        "repo_data",
        "configuration",
        "configuration_path",
    },
}


class SubmitBody(CoreModel):
    run: Run
    job_spec: JobSpec
    job_submission: JobSubmission
    cluster_info: Optional[ClusterInfo] = None
    secrets: Optional[Dict[str, str]] = None
    repo_credentials: Optional[RemoteRepoCreds] = None
    log_quota_hour: Optional[int] = None
    """Maximum bytes of log output per hour. None means unlimited."""
    # TODO: remove `run_spec` once instances deployed with 0.19.8 or earlier are no longer supported.
    run_spec: RunSpec
    """`run_spec` is deprecated in favor of `run.run_spec`."""

    def json_for_runner(self) -> str:
        """The JSON the runner is sent, restricted to `_SUBMIT_BODY_INCLUDE`."""
        return self.model_dump_json(include=_SUBMIT_BODY_INCLUDE)


class HealthcheckResponse(CoreModel):
    service: str
    version: str


class InstanceHealthResponse(CoreModel):
    dcgm: Optional[DCGMHealthResponse] = None


class ShutdownRequest(CoreModel):
    force: bool


class ComponentName(str, Enum):
    RUNNER = "dstack-runner"
    SHIM = "dstack-shim"


class ComponentStatus(str, Enum):
    NOT_INSTALLED = "not-installed"
    INSTALLED = "installed"
    INSTALLING = "installing"
    ERROR = "error"


class ComponentInfo(CoreModel):
    name: str
    """`name` does not use `ComponentName` so newer shim versions remain compatible with the older server."""
    version: str
    status: ComponentStatus


class ComponentListResponse(CoreModel):
    components: list[ComponentInfo]


class ComponentInstallRequest(CoreModel):
    name: ComponentName
    url: str


class GPUMetrics(CoreModel):
    gpu_memory_usage_bytes: int
    gpu_util_percent: int


class MetricsResponse(CoreModel):
    timestamp_micro: int
    cpu_usage_micro: int
    memory_usage_bytes: int
    memory_working_set_bytes: int
    gpus: List[GPUMetrics]


class ShimVolumeInfo(CoreModel):
    backend: str
    name: str
    volume_id: str
    init_fs: bool
    device_name: Optional[str] = None


class PortMapping(CoreModel):
    host: int
    container: int


class TaskStatus(str, Enum):
    PENDING = "pending"
    PREPARING = "preparing"
    PULLING = "pulling"
    CREATING = "creating"
    RUNNING = "running"
    TERMINATED = "terminated"


class GPUDevice(CoreModel):
    path_on_host: str
    path_in_container: str


class TaskListItem(CoreModel):
    id: str
    status: TaskStatus


class TaskListResponse(CoreModel):
    ids: Optional[list[str]] = None
    """`ids` is returned by pre-0.19.26 shim versions."""
    tasks: Optional[list[TaskListItem]] = None
    """`tasks` is returned by shim versions 0.19.26 and newer."""


class TaskInfoResponse(CoreModel):
    id: str
    status: TaskStatus
    termination_reason: str
    termination_message: str
    ports: Optional[list[PortMapping]] = []
    """`ports` uses a default value for backward compatibility with 0.18.34.
    It can be removed after a few releases.
    """
    image_pull_progress: Optional[ImagePullProgress] = None


class TaskSubmitRequest(CoreModel):
    id: str
    name: str
    registry_username: str
    registry_password: str
    image_name: str
    container_user: str
    privileged: bool
    gpu: int
    cpu: float
    memory: int
    shm_size: int
    network_mode: NetworkMode
    volumes: list[ShimVolumeInfo]
    volume_mounts: list[VolumeMountPoint]
    instance_mounts: list[InstanceMountPoint]
    gpu_devices: list[GPUDevice]
    host_ssh_user: str
    host_ssh_keys: list[str]
    container_ssh_keys: list[str]


class TaskTerminateRequest(CoreModel):
    termination_reason: str
    termination_message: str
    timeout: int


class LegacySubmitBody(CoreModel):
    username: str
    password: str
    image_name: str
    privileged: bool
    container_name: str
    container_user: str
    shm_size: int
    public_keys: List[str]
    ssh_user: str
    ssh_key: str
    mounts: List[VolumeMountPoint]
    volumes: List[ShimVolumeInfo]
    instance_mounts: List[InstanceMountPoint]


class LegacyStopBody(CoreModel):
    force: bool = False


class JobResult(CoreModel):
    reason: str
    reason_message: str


class LegacyPullResponse(CoreModel):
    state: str
    result: Optional[JobResult] = None
