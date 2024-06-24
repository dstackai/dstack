from base64 import b64decode
from typing import Dict, List, Optional, Union

from pydantic import Field, validator
from typing_extensions import Annotated

from dstack._internal.core.models.common import CoreModel
from dstack._internal.core.models.repos.remote import RemoteRepoCreds
from dstack._internal.core.models.runs import ClusterInfo, JobSpec, JobStatus, RunSpec
from dstack._internal.core.models.volumes import VolumeMountPoint


class JobStateEvent(CoreModel):
    timestamp: int
    state: JobStatus


class LogEvent(CoreModel):
    timestamp: int  # nanoseconds
    message: bytes

    @validator("message", pre=True)
    def decode_message(cls, v: Union[str, bytes]) -> bytes:
        if isinstance(v, str):
            return b64decode(v)
        return v


class PullResponse(CoreModel):
    job_states: List[JobStateEvent]
    job_logs: List[LogEvent]
    runner_logs: List[LogEvent]
    last_updated: int


class SubmitBody(CoreModel):
    run_spec: Annotated[
        RunSpec,
        Field(
            include={
                "run_name",
                "repo_id",
                "repo_data",
                "configuration",
                "configuration_path",
            }
        ),
    ]
    job_spec: Annotated[
        JobSpec,
        Field(
            include={
                "replica_num",
                "job_num",
                "jobs_per_replica",
                "commands",
                "entrypoint",
                "env",
                "gateway",
                "max_duration",
                "working_dir",
            }
        ),
    ]
    cluster_info: Annotated[Optional[ClusterInfo], Field(include=True)]
    secrets: Annotated[Optional[Dict[str, str]], Field(include=True)]
    repo_credentials: Annotated[Optional[RemoteRepoCreds], Field(include=True)]


class HealthcheckResponse(CoreModel):
    service: str
    version: str


class ShimVolumeInfo(CoreModel):
    name: str
    volume_id: str
    init_fs: bool


class TaskConfigBody(CoreModel):
    username: str
    password: str
    image_name: str
    container_name: str
    shm_size: int
    public_keys: List[str]
    ssh_user: str
    ssh_key: str
    mounts: List[VolumeMountPoint]
    volumes: List[ShimVolumeInfo]


class StopBody(CoreModel):
    force: bool = False


class JobResult(CoreModel):
    reason: str
    reason_message: str


class PullBody(CoreModel):
    state: str
    executor_error: Optional[str]
    container_name: Optional[str]
    status: Optional[str]
    running: Optional[bool]
    oom_killed: Optional[bool]
    dead: Optional[bool]
    exit_code: Optional[int]
    error: Optional[str]
    result: Optional[JobResult]
