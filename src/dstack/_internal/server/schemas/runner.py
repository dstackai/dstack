from base64 import b64decode
from typing import Dict, List, Optional, Union

from pydantic import BaseModel, Field, validator
from typing_extensions import Annotated

from dstack._internal.core.models.repos.remote import RemoteRepoCreds
from dstack._internal.core.models.runs import JobSpec, JobStatus, RunSpec


class JobStateEvent(BaseModel):
    timestamp: int
    state: JobStatus


class LogEvent(BaseModel):
    timestamp: int  # nanoseconds
    message: bytes

    @validator("message", pre=True)
    def decode_message(cls, v: Union[str, bytes]) -> bytes:
        if isinstance(v, str):
            return b64decode(v)
        return v


class PullResponse(BaseModel):
    job_states: List[JobStateEvent]
    job_logs: List[LogEvent]
    runner_logs: List[LogEvent]
    last_updated: int


class SubmitBody(BaseModel):
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
                "commands",
                "entrypoint",
                "env",
                "gateway",
                "max_duration",
                "working_dir",
            }
        ),
    ]
    secrets: Annotated[Optional[Dict[str, str]], Field(include=True)]
    repo_credentials: Annotated[Optional[RemoteRepoCreds], Field(include=True)]


class HealthcheckResponse(BaseModel):
    service: str
    version: str


class DockerImageBody(BaseModel):
    username: str
    password: str
    image_name: str
    container_name: str
    shm_size: int


class StopBody(BaseModel):
    force: bool = False


class PullBody(BaseModel):
    state: str
    container_name: Optional[str]
    status: Optional[str]
    running: Optional[bool]
    oom_killed: Optional[bool]
    dead: Optional[bool]
    exit_code: Optional[int]
    error: Optional[str]
