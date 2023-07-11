from abc import abstractmethod
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field, root_validator

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


class GpusRequirements(BaseModel):
    count: Optional[int] = None
    memory_mib: Optional[int] = None
    name: Optional[str] = None


class Requirements(BaseModel):
    cpus: Optional[int] = None
    memory_mib: Optional[int] = None
    gpus: Optional[GpusRequirements] = None
    shm_size_mib: Optional[int] = None
    spot: Optional[bool] = None
    local: Optional[bool] = None

    def serialize(self) -> Dict[str, Any]:
        req_data = {}
        if self.cpus:
            req_data["cpus"] = self.cpus
        if self.memory_mib:
            req_data["memory_mib"] = self.memory_mib
        if self.gpus:
            req_data["gpus"] = {"count": self.gpus.count}
            if self.gpus.memory_mib:
                req_data["gpus"]["memory_mib"] = self.gpus.memory_mib
            if self.gpus.name:
                req_data["gpus"]["name"] = self.gpus.name
        if self.shm_size_mib:
            req_data["shm_size_mib"] = self.shm_size_mib
        if self.spot:
            req_data["spot"] = self.spot
        if self.local:
            req_data["local"] = self.local
        return req_data


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


class JobStatus(str, Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    DOWNLOADING = "downloading"
    BUILDING = "building"
    RUNNING = "running"
    UPLOADING = "uploading"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ABORTING = "aborting"
    ABORTED = "aborted"
    FAILED = "failed"
    DONE = "done"

    def is_finished(self):
        return self in [self.STOPPED, self.ABORTED, self.FAILED, self.DONE]

    def is_unfinished(self):
        return not self.is_finished()


class SpotPolicy(str, Enum):
    SPOT = "spot"
    ONDEMAND = "on-demand"
    AUTO = "auto"


class RetryPolicy(BaseModel):
    retry: bool
    limit: Optional[int]


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
    workflow_name: Optional[str]
    provider_name: str
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

    def get_id(self) -> Optional[str]:
        return self.job_id

    def set_id(self, job_id: Optional[str]):
        self.job_id = job_id


class RegistryAuth(BaseModel):
    username: Optional[str] = None
    password: Optional[str] = None

    def serialize(self) -> Dict[str, Any]:
        return self.dict(exclude_none=True)


def check_dict(element: Any, field: str):
    if type(element) == dict:
        return element.get(field)
    if hasattr(element, field):
        return getattr(element, field)
    return None


class Job(JobHead):
    job_id: Optional[str]
    repo_data: Union[RepoData, RemoteRepoData, LocalRepoData] = Field(
        ..., discriminator="repo_type"
    )
    repo_code_filename: Optional[str] = None
    run_name: str
    workflow_name: Optional[str]  # deprecated
    provider_name: Optional[str]  # deprecated
    configuration_type: Optional[ConfigurationType]
    configuration_path: Optional[str]
    status: JobStatus
    error_code: Optional[JobErrorCode]
    container_exit_code: Optional[int]
    created_at: int
    submitted_at: int
    submission_num: int = 1
    image_name: str
    registry_auth: Optional[RegistryAuth]
    commands: Optional[List[str]]
    entrypoint: Optional[List[str]]
    env: Optional[Dict[str, str]]
    home_dir: Optional[str]
    working_dir: Optional[str]
    artifact_specs: Optional[List[ArtifactSpec]]
    cache_specs: List[CacheSpec]
    host_name: Optional[str]
    requirements: Optional[Requirements]
    spot_policy: Optional[SpotPolicy]
    retry_policy: Optional[RetryPolicy]
    dep_specs: Optional[List[DepSpec]]
    master_job: Optional[JobRef]
    app_specs: Optional[List[AppSpec]]
    runner_id: Optional[str]
    request_id: Optional[str]
    location: Optional[str]
    tag_name: Optional[str]
    ssh_key_pub: Optional[str]
    build_policy: BuildPolicy = BuildPolicy.USE_BUILD
    build_commands: Optional[List[str]]
    optional_build_commands: Optional[List[str]]
    run_env: Optional[Dict[str, str]]  # deprecated

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
        deps = []
        if self.dep_specs:
            for dep in self.dep_specs:
                deps.append(
                    {
                        "repo_id": dep.repo_ref.repo_id,
                        "hub_user_name": self.hub_user_name,
                        "run_name": dep.run_name,
                        "mount": dep.mount,
                    }
                )
        artifacts = []
        if self.artifact_specs:
            for artifact_spec in self.artifact_specs:
                artifacts.append(
                    {"path": artifact_spec.artifact_path, "mount": artifact_spec.mount}
                )
        job_data = {
            "job_id": self.job_id,
            "repo_id": self.repo.repo_id,
            "hub_user_name": self.hub_user_name,
            "repo_type": self.repo.repo_data.repo_type,
            "run_name": self.run_name,
            "workflow_name": self.workflow_name or "",
            "provider_name": self.provider_name,
            "configuration_type": self.configuration_type.value
            if self.configuration_type
            else None,
            "configuration_path": self.configuration_path,
            "status": self.status.value,
            "error_code": self.error_code.value if self.error_code is not None else "",
            "container_exit_code": self.container_exit_code or "",
            "created_at": self.created_at,
            "submitted_at": self.submitted_at,
            "submission_num": self.submission_num,
            "image_name": self.image_name,
            "registry_auth": self.registry_auth.serialize() if self.registry_auth else {},
            "commands": self.commands or [],
            "entrypoint": self.entrypoint,
            "env": self.env or {},
            "home_dir": self.home_dir or "",
            "working_dir": self.working_dir or "",
            "artifacts": artifacts,
            "cache": [item.dict() for item in self.cache_specs],
            "host_name": self.host_name or "",
            "spot_policy": self.spot_policy.value if self.spot_policy else None,
            "retry_policy": self.retry_policy.dict() if self.retry_policy else None,
            "requirements": self.requirements.serialize() if self.requirements else {},
            "deps": deps,
            "master_job_id": self.master_job.get_id() if self.master_job else "",
            "apps": [
                {
                    "port": a.port,
                    "map_to_port": a.map_to_port,
                    "app_name": a.app_name,
                    "url_path": a.url_path or "",
                    "url_query_params": a.url_query_params or {},
                }
                for a in self.app_specs
            ]
            if self.app_specs
            else [],
            "runner_id": self.runner_id or "",
            "request_id": self.request_id or "",
            "location": self.location or "",
            "tag_name": self.tag_name or "",
            "ssh_key_pub": self.ssh_key_pub or "",
            "repo_code_filename": self.repo_code_filename,
            "instance_type": self.instance_type,
            "build_policy": self.build_policy.value,
            "build_commands": self.build_commands or [],
            "optional_build_commands": self.optional_build_commands or [],
            "run_env": self.run_env or {},
        }
        if isinstance(self.repo_data, RemoteRepoData):
            job_data["repo_host_name"] = self.repo_data.repo_host_name
            job_data["repo_port"] = self.repo_data.repo_port or 0
            job_data["repo_user_name"] = self.repo_data.repo_user_name
            job_data["repo_name"] = self.repo_data.repo_name
            job_data["repo_branch"] = self.repo_data.repo_branch or ""
            job_data["repo_hash"] = self.repo_data.repo_hash or ""
            job_data["repo_config_name"] = self.repo_data.repo_config_name or ""
            job_data["repo_config_email"] = self.repo_data.repo_config_email or ""
        return job_data

    @staticmethod
    def unserialize(job_data: dict):
        _requirements = job_data.get("requirements")
        requirements = (
            Requirements(
                cpus=_requirements.get("cpus") or None,
                memory_mib=_requirements.get("memory_mib") or None,
                gpus=GpusRequirements(
                    count=_requirements["gpus"].get("count") or None,
                    memory_mib=_requirements["gpus"].get("memory") or None,
                    name=_requirements["gpus"].get("name") or None,
                )
                if _requirements.get("gpus")
                else None,
                shm_size_mib=_requirements.get("shm_size_mib") or None,
                spot=_requirements.get("spot") or _requirements.get("interruptible"),
                local=_requirements.get("local") or None,
            )
            if _requirements
            else Requirements()
        )
        spot_policy = job_data.get("spot_policy")
        retry_policy = None
        if job_data.get("retry_policy") is not None:
            retry_policy = RetryPolicy.parse_obj(job_data.get("retry_policy"))
        dep_specs = []
        if job_data.get("deps"):
            for dep in job_data["deps"]:
                dep_spec = DepSpec(
                    repo_ref=RepoRef(repo_id=dep["repo_id"]),
                    run_name=dep["run_name"],
                    mount=dep.get("mount") is True,
                )
                dep_specs.append(dep_spec)
        artifact_specs = []
        if job_data.get("artifacts"):
            for artifact in job_data["artifacts"]:
                if isinstance(artifact, str):
                    artifact_spec = ArtifactSpec(artifact_path=artifact, mount=False)
                else:
                    artifact_spec = ArtifactSpec(
                        artifact_path=artifact["path"], mount=artifact.get("mount") is True
                    )
                artifact_specs.append(artifact_spec)
        master_job = (
            JobRefId(job_id=job_data["master_job_id"]) if job_data.get("master_job_id") else None
        )
        app_specs = (
            [
                AppSpec(
                    port=a.get("port", 0),
                    map_to_port=a.get("map_to_port"),
                    app_name=a["app_name"],
                    url_path=a.get("url_path") or None,
                    url_query_params=a.get("url_query_params") or None,
                )
                for a in (job_data.get("apps") or [])
            ]
        ) or None
        error_code = job_data.get("error_code")
        container_exit_code = job_data.get("container_exit_code")
        configuration_type = job_data.get("configuration_type")

        if job_data["repo_type"] == "remote":
            repo_data = RemoteRepoData(
                repo_host_name=job_data["repo_host_name"],
                repo_port=job_data.get("repo_port") or None,
                repo_user_name=job_data["repo_user_name"],
                repo_name=job_data["repo_name"],
                repo_branch=job_data.get("repo_branch") or None,
                repo_hash=job_data.get("repo_hash") or None,
                repo_config_name=job_data.get("repo_config_name") or None,
                repo_config_email=job_data.get("repo_config_email") or None,
            )
        elif job_data["repo_type"] == "local":
            repo_data = LocalRepoData(repo_dir=job_data.get("repo_dir", ""))
        else:
            raise TypeError(f"Unknown repo_type: {job_data['repo_type']}")

        job = Job(
            job_id=job_data["job_id"],
            repo_ref=RepoRef(repo_id=job_data["repo_id"]),
            hub_user_name=job_data["hub_user_name"],
            repo_data=repo_data,
            repo_code_filename=job_data.get("repo_code_filename"),
            run_name=job_data["run_name"],
            workflow_name=job_data.get("workflow_name") or None,
            provider_name=job_data["provider_name"],
            configuration_type=ConfigurationType(configuration_type)
            if configuration_type
            else None,
            configuration_path=job_data.get("configuration_path"),
            status=JobStatus(job_data["status"]),
            error_code=JobErrorCode(error_code) if error_code else None,
            container_exit_code=int(container_exit_code) if container_exit_code else None,
            created_at=job_data.get("created_at") or job_data["submitted_at"],
            submitted_at=job_data["submitted_at"],
            submission_num=job_data.get("submission_num") or 1,
            image_name=job_data["image_name"],
            registry_auth=RegistryAuth(**job_data.get("registry_auth", {})),
            commands=job_data.get("commands") or None,
            entrypoint=job_data.get("entrypoint") or None,
            env=job_data["env"] or None,
            home_dir=job_data.get("home_dir") or None,
            working_dir=job_data.get("working_dir") or None,
            artifact_specs=artifact_specs,
            cache_specs=[CacheSpec(**item) for item in job_data.get("cache", [])],
            host_name=job_data.get("host_name") or None,
            spot_policy=SpotPolicy(spot_policy) if spot_policy else None,
            retry_policy=retry_policy,
            requirements=requirements,
            dep_specs=dep_specs or None,
            master_job=master_job,
            app_specs=app_specs,
            runner_id=job_data.get("runner_id") or None,
            request_id=job_data.get("request_id") or None,
            location=job_data.get("location") or None,
            tag_name=job_data.get("tag_name") or None,
            ssh_key_pub=job_data.get("ssh_key_pub") or None,
            instance_type=job_data.get("instance_type") or None,
            build_policy=job_data.get("build_policy") or BuildPolicy.USE_BUILD,
            build_commands=job_data.get("build_commands") or None,
            optional_build_commands=job_data.get("optional_build_commands") or None,
            run_env=job_data.get("run_env") or None,
        )
        return job

    @property
    def repo(self) -> Repo:
        if isinstance(self.repo_data, RemoteRepoData):
            return RemoteRepo(repo_ref=self.repo_ref, repo_data=self.repo_data)
        elif isinstance(self.repo_data, LocalRepoData):
            return LocalRepo(repo_ref=self.repo_ref, repo_data=self.repo_data)


class JobSpec(JobRef):
    image_name: str
    job_id: Optional[str] = None
    registry_auth: Optional[RegistryAuth] = None
    commands: Optional[List[str]] = None
    entrypoint: Optional[List[str]] = None
    env: Optional[Dict[str, str]] = None
    run_env: Optional[Dict[str, str]] = None
    working_dir: Optional[str] = None
    artifact_specs: Optional[List[ArtifactSpec]] = None
    requirements: Optional[Requirements] = None
    master_job: Optional[JobRef] = None
    app_specs: Optional[List[AppSpec]] = None
    build_commands: Optional[List[str]] = None

    def get_id(self) -> Optional[str]:
        return self.job_id

    def set_id(self, job_id: Optional[str]):
        self.job_id = job_id
