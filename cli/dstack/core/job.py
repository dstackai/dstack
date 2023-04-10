from abc import abstractmethod
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from dstack.core.app import AppSpec
from dstack.core.artifact import ArtifactSpec
from dstack.core.cache import CacheSpec
from dstack.core.dependents import DepSpec
from dstack.core.repo import RepoAddress, RepoData
from dstack.utils.common import _quoted, format_list


class GpusRequirements(BaseModel):
    count: Optional[int] = None
    memory_mib: Optional[int] = None
    name: Optional[str] = None

    def __str__(self) -> str:
        return (
            f"GpusRequirements(count={self.count}, memory_mib={self.memory_mib}, "
            f"name={_quoted(self.name)})"
        )


class Requirements(BaseModel):
    cpus: Optional[int] = None
    memory_mib: Optional[int] = None
    gpus: Optional[GpusRequirements] = None
    shm_size_mib: Optional[int] = None
    interruptible: Optional[bool] = None
    local: Optional[bool] = None

    def __str__(self) -> str:
        return (
            f"Requirements(cpus={self.cpus}, memory_mib={self.memory_mib}, "
            f"gpus={self.gpus}, "
            f"shm_size_mib={self.shm_size_mib}, "
            f"interruptible={self.interruptible}, "
            f"local={self.local})"
        )

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
        if self.interruptible:
            req_data["interruptible"] = self.interruptible
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

    def __str__(self) -> str:
        return f'JobRefId(job_id="{self.job_id}")'


class JobStatus(Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    DOWNLOADING = "downloading"
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


class JobHead(JobRef):
    job_id: str
    repo_address: RepoAddress
    run_name: str
    workflow_name: Optional[str]
    provider_name: str
    local_repo_user_name: Optional[str]
    status: JobStatus
    submitted_at: int
    artifact_paths: Optional[List[str]]
    tag_name: Optional[str]
    app_names: Optional[List[str]]

    def get_id(self) -> Optional[str]:
        return self.job_id

    def set_id(self, job_id: Optional[str]):
        self.job_id = job_id

    def __str__(self) -> str:
        artifact_paths = (
            ("[" + ", ".join(map(lambda a: _quoted(str(a)), self.artifact_paths)) + "]")
            if self.artifact_paths
            else None
        )
        app_names = (
            ("[" + ", ".join(map(lambda a: _quoted(a), self.app_names)) + "]")
            if self.app_names
            else None
        )
        return (
            f'JobHead(job_id="{self.job_id}", repo_address={self.repo_address}, '
            f'run_name="{self.run_name}", workflow_name={_quoted(self.workflow_name)}, '
            f'provider_name="{self.provider_name}", '
            f"local_repo_user_name={_quoted(self.local_repo_user_name)}, "
            f"status=JobStatus.{self.status.name}, "
            f"submitted_at={self.submitted_at}, "
            f"artifact_paths={artifact_paths}, "
            f"tag_name={_quoted(self.tag_name)}, "
            f"app_names={app_names})"
        )


class RegistryAuth(BaseModel):
    username: Optional[str] = None
    password: Optional[str] = None

    def __str__(self) -> str:
        return f"RegistryCredentials(username={self.username}, password={self.password})"

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
    repo_data: RepoData
    run_name: str
    workflow_name: Optional[str]
    provider_name: str
    local_repo_user_name: Optional[str]
    local_repo_user_email: Optional[str]
    status: JobStatus
    submitted_at: int
    submission_num: int = 1
    image_name: str
    registry_auth: Optional[RegistryAuth]
    commands: Optional[List[str]]
    entrypoint: Optional[List[str]]
    env: Optional[Dict[str, str]]
    working_dir: Optional[str]
    artifact_specs: Optional[List[ArtifactSpec]]
    cache_specs: List[CacheSpec]
    port_count: Optional[int]
    ports: Optional[List[int]]
    host_name: Optional[str]
    requirements: Optional[Requirements]
    dep_specs: Optional[List[DepSpec]]
    master_job: Optional[JobRef]
    app_specs: Optional[List[AppSpec]]
    runner_id: Optional[str]
    request_id: Optional[str]
    tag_name: Optional[str]
    ssh_key_pub: Optional[str]

    def __init__(self, **data: Any):
        # TODO Ugly style
        if type(data) == dict:
            if "repo_address" in data:
                del data["repo_address"]
            if "artifact_paths" in data:
                del data["artifact_paths"]
            if "app_names" in data:
                del data["app_names"]
        super().__init__(
            repo_address=data.get("repo_data"),
            artifact_paths=[check_dict(a, "artifact_path") for a in data.get("artifact_specs")]
            if data.get("artifact_specs")
            else None,
            app_names=[check_dict(a, "app_name") for a in data.get("app_specs")]
            if data.get("app_specs")
            else None,
            **data,
        )

    def get_id(self) -> Optional[str]:
        return self.job_id

    def set_id(self, job_id: Optional[str]):
        self.job_id = job_id

    def __str__(self) -> str:
        commands = format_list(self.commands, formatter=lambda a: _quoted(str(a)))
        entrypoint = format_list(self.entrypoint, formatter=lambda a: _quoted(str(a)))
        artifact_specs = format_list(self.artifact_specs)
        cache_specs = format_list(self.cache_specs or None)
        app_specs = format_list(self.app_specs)
        dep_specs = format_list(self.dep_specs)
        ssk_key_pub = f"...{self.ssh_key_pub[-16:]}" if self.ssh_key_pub else None
        return (
            f'Job(job_id="{self.job_id}", repo_data={self.repo_data}, '
            f'run_name="{self.run_name}", workflow_name={_quoted(self.workflow_name)}, '
            f'provider_name="{self.provider_name}", '
            f"local_repo_user_name={_quoted(self.local_repo_user_name)}, "
            f"local_repo_user_email={_quoted(self.local_repo_user_email)}, "
            f"status=JobStatus.{self.status.name}, "
            f"submitted_at={self.submitted_at}, "
            f'image_name="{self.image_name}", '
            f'registry_auth="{self.registry_auth}", '
            f"commands={commands}, "
            f"entrypoint={entrypoint}, "
            f"env={self.env}, "
            f"working_dir={_quoted(self.working_dir)}, "
            f"port_count={self.port_count}, "
            f"ports={self.ports}, "
            f"host_name={_quoted(self.host_name)}, "
            f"artifact_specs={artifact_specs}, "
            f"cache_specs={cache_specs}, "
            f"requirements={self.requirements}, "
            f"dep_specs={dep_specs}, "
            f"master_job={self.master_job}, "
            f"app_specs={app_specs}, "
            f"runner_id={_quoted(self.runner_id)}, "
            f"request_id={_quoted(self.request_id)}, "
            f"tag_name={_quoted(self.tag_name)}"
            f"ssh_key_pub={_quoted(ssk_key_pub)})"
        )

    def serialize(self) -> dict:
        deps = []
        if self.dep_specs:
            for dep in self.dep_specs:
                deps.append(
                    {
                        "repo_host_name": dep.repo_address.repo_host_name,
                        "repo_port": dep.repo_address.repo_port or 0,
                        "repo_user_name": dep.repo_address.repo_user_name,
                        "repo_name": dep.repo_address.repo_name,
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
            "repo_host_name": self.repo_address.repo_host_name,
            "repo_port": self.repo_address.repo_port or 0,
            "repo_user_name": self.repo_data.repo_user_name,
            "repo_name": self.repo_data.repo_name,
            "repo_branch": self.repo_data.repo_branch or "",
            "repo_hash": self.repo_data.repo_hash or "",
            "repo_diff": self.repo_data.repo_diff or "",
            "run_name": self.run_name,
            "workflow_name": self.workflow_name or "",
            "provider_name": self.provider_name,
            "local_repo_user_name": self.local_repo_user_name or "",
            "local_repo_user_email": self.local_repo_user_email or "",
            "status": self.status.value,
            "submitted_at": self.submitted_at,
            "submission_num": self.submission_num,
            "image_name": self.image_name,
            "registry_auth": self.registry_auth.serialize() if self.registry_auth else {},
            "commands": self.commands or [],
            "entrypoint": self.entrypoint,
            "env": self.env or {},
            "working_dir": self.working_dir or "",
            "artifacts": artifacts,
            "cache": [item.dict() for item in self.cache_specs],
            "port_count": self.port_count if self.port_count else 0,
            "ports": [str(port) for port in self.ports] if self.ports else [],
            "host_name": self.host_name or "",
            "requirements": self.requirements.serialize() if self.requirements else {},
            "deps": deps,
            "master_job_id": self.master_job.get_id() if self.master_job else "",
            "apps": [
                {
                    "port_index": a.port_index,
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
            "tag_name": self.tag_name or "",
            "ssh_key_pub": self.ssh_key_pub or "",
        }
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
                    memory=_requirements["gpus"].get("memory") or None,
                    name=_requirements["gpus"].get("name") or None,
                )
                if _requirements.get("gpus")
                else None,
                shm_size_mib=_requirements.get("shm_size_mib") or None,
                interruptible=_requirements.get("interruptible") or None,
                local=_requirements.get("local") or None,
            )
            if _requirements
            else None
        )
        if requirements:
            if (
                not requirements.cpus
                and (
                    not requirements.gpus
                    or (
                        not requirements.gpus.count
                        and not requirements.gpus.memory_mib
                        and not requirements.gpus.name
                    )
                )
                and not requirements.interruptible
                and not requirements.local
                and not not requirements.shm_size_mib
            ):
                requirements = None
        dep_specs = []
        if job_data.get("deps"):
            for dep in job_data["deps"]:
                dep_spec = DepSpec(
                    repo_address=RepoAddress(
                        repo_host_name=dep["repo_host_name"],
                        repo_port=dep.get("repo_port") or None,
                        repo_user_name=dep["repo_user_name"],
                        repo_name=dep["repo_name"],
                    ),
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
                    port_index=a["port_index"],
                    app_name=a["app_name"],
                    url_path=a.get("url_path") or None,
                    url_query_params=a.get("url_query_params") or None,
                )
                for a in (job_data.get("apps") or [])
            ]
        ) or None
        job = Job(
            job_id=job_data["job_id"],
            repo_data=RepoData(
                repo_host_name=job_data["repo_host_name"],
                repo_port=job_data.get("repo_port") or None,
                repo_user_name=job_data["repo_user_name"],
                repo_name=job_data["repo_name"],
                repo_branch=job_data["repo_branch"] or None,
                repo_hash=job_data["repo_hash"] or None,
                repo_diff=job_data["repo_diff"] or None,
            ),
            run_name=job_data["run_name"],
            workflow_name=job_data.get("workflow_name") or None,
            provider_name=job_data["provider_name"],
            local_repo_user_name=job_data.get("local_repo_user_name"),
            local_repo_user_email=job_data.get("local_repo_user_email") or None,
            status=JobStatus(job_data["status"]),
            submitted_at=job_data["submitted_at"],
            submission_num=job_data.get("submission_num") or 1,
            image_name=job_data["image_name"],
            registry_auth=RegistryAuth(**job_data.get("registry_auth", {})),
            commands=job_data.get("commands") or None,
            entrypoint=job_data.get("entrypoint") or None,
            env=job_data["env"] or None,
            working_dir=job_data.get("working_dir") or None,
            artifact_specs=artifact_specs,
            cache_specs=[CacheSpec(**item) for item in job_data.get("cache", [])],
            port_count=job_data.get("port_count") or None,
            ports=job_data.get("ports") or None,
            host_name=job_data.get("host_name") or None,
            requirements=requirements,
            dep_specs=dep_specs or None,
            master_job=master_job,
            app_specs=app_specs,
            runner_id=job_data.get("runner_id") or None,
            request_id=job_data.get("request_id") or None,
            tag_name=job_data.get("tag_name") or None,
            ssh_key_pub=job_data.get("ssh_key_pub") or None,
        )
        return job


class JobSpec(JobRef):
    image_name: str
    registry_auth: Optional[RegistryAuth] = None
    commands: Optional[List[str]] = None
    entrypoint: Optional[List[str]] = None
    env: Optional[Dict[str, str]] = None
    working_dir: Optional[str] = None
    artifact_specs: Optional[List[ArtifactSpec]] = None
    port_count: Optional[int] = None
    requirements: Optional[Requirements] = None
    master_job: Optional[JobRef] = None
    app_specs: Optional[List[AppSpec]] = None

    def get_id(self) -> Optional[str]:
        return self.job_id

    def set_id(self, job_id: Optional[str]):
        self.job_id = job_id

    def __str__(self) -> str:
        commands = format_list(self.commands, formatter=lambda a: _quoted(str(a)))
        entrypoint = format_list(self.entrypoint, formatter=lambda a: _quoted(str(a)))
        artifact_specs = format_list(self.artifact_specs)
        app_specs = format_list(self.app_specs)
        return (
            f'JobSpec(job_id="{self.job_id}", image_name="{self.image_name}", '
            f"registry_auth={self.registry_auth}, "
            f"commands={commands}, "
            f"entrypoint={entrypoint}, "
            f"env={self.env}, "
            f"working_dir={_quoted(self.working_dir)}, "
            f"port_count={self.port_count}, "
            f"artifact_specs={artifact_specs}, "
            f"requirements={self.requirements}, "
            f"master_job={self.master_job}, "
            f"app_specs={app_specs})"
        )
