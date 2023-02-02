from abc import abstractmethod
from enum import Enum
from typing import Optional, List, Dict, Any

from dstack.core.artifact import ArtifactSpec
from dstack.core.app import AppSpec
from dstack.core.dependents import DepSpec
from dstack.core.repo import RepoData, RepoAddress
from dstack.utils.common import _quoted


class GpusRequirements:
    def __init__(
        self,
        count: Optional[int] = None,
        memory_mib: Optional[int] = None,
        name: Optional[str] = None,
    ):
        self.count = count
        self.memory_mib = memory_mib
        self.name = name

    def __str__(self) -> str:
        return (
            f"GpusRequirements(count={self.count}, memory_mib={self.memory_mib}, "
            f"name={_quoted(self.name)})"
        )


class Requirements:
    def __init__(
        self,
        cpus: Optional[int] = None,
        memory_mib: Optional[int] = None,
        gpus: Optional[GpusRequirements] = None,
        shm_size_mib: Optional[int] = None,
        interruptible: Optional[bool] = None,
        local: Optional[bool] = None,
    ):
        self.cpus = cpus
        self.memory_mib = memory_mib
        self.gpus = gpus
        self.shm_size_mib = shm_size_mib
        self.interruptible = interruptible
        self.local = local

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


class JobRef:
    @abstractmethod
    def get_id(self) -> Optional[str]:
        pass

    @abstractmethod
    def set_id(self, job_id: Optional[str]):
        pass


class JobRefId(JobRef):
    def get_id(self) -> Optional[str]:
        return self.job_id

    def set_id(self, job_id: Optional[str]):
        self.job_id = job_id

    def __init__(self, job_id: str):
        self.job_id = job_id

    def __str__(self) -> str:
        return f'JobRefId(job_id="{self.job_id}")'


class JobStatus(Enum):
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
    def __init__(
        self,
        job_id: str,
        repo_address: RepoAddress,
        run_name: str,
        workflow_name: Optional[str],
        provider_name: str,
        local_repo_user_name: Optional[str],
        status: JobStatus,
        submitted_at: int,
        artifact_paths: Optional[List[str]],
        tag_name: Optional[str],
        app_names: Optional[List[str]],
    ):
        self.job_id = job_id
        self.repo_address = repo_address
        self.run_name = run_name
        self.workflow_name = workflow_name
        self.provider_name = provider_name
        self.local_repo_user_name = local_repo_user_name
        self.status = status
        self.submitted_at = submitted_at
        self.artifact_paths = artifact_paths
        self.tag_name = tag_name
        self.app_names = app_names

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


class Job(JobHead):
    def __init__(
        self,
        job_id: Optional[str],
        repo_data: RepoData,
        run_name: str,
        workflow_name: Optional[str],
        provider_name: str,
        local_repo_user_name: Optional[str],
        local_repo_user_email: Optional[str],
        status: JobStatus,
        submitted_at: int,
        image_name: str,
        commands: Optional[List[str]],
        env: Optional[Dict[str, str]],
        working_dir: Optional[str],
        artifact_specs: Optional[List[ArtifactSpec]],
        port_count: Optional[int],
        ports: Optional[List[int]],
        host_name: Optional[str],
        requirements: Optional[Requirements],
        dep_specs: Optional[List[DepSpec]],
        master_job: Optional[JobRef],
        app_specs: Optional[List[AppSpec]],
        runner_id: Optional[str],
        request_id: Optional[str],
        tag_name: Optional[str],
    ):
        super().__init__(
            job_id,
            repo_data,
            run_name,
            workflow_name,
            provider_name,
            local_repo_user_name,
            status,
            submitted_at,
            [a.artifact_path for a in artifact_specs] if artifact_specs else None,
            tag_name,
            [a.app_name for a in app_specs] if app_specs else None,
        )
        self.repo_data = repo_data
        self.local_repo_user_email = local_repo_user_email
        self.runner_id = runner_id
        self.request_id = request_id
        self.image_name = image_name
        self.commands = commands
        self.env = env
        self.working_dir = working_dir
        self.artifact_specs = artifact_specs
        self.port_count = port_count
        self.ports = ports
        self.host_name = host_name
        self.requirements = requirements
        self.dep_specs = dep_specs
        self.master_job = master_job
        self.app_specs = app_specs

    def get_id(self) -> Optional[str]:
        return self.job_id

    def set_id(self, job_id: Optional[str]):
        self.job_id = job_id

    def __str__(self) -> str:
        commands = (
            ("[" + ", ".join(map(lambda a: _quoted(str(a)), self.commands)) + "]")
            if self.commands
            else None
        )
        artifact_specs = (
            ("[" + ", ".join(map(lambda a: _quoted(str(a)), self.artifact_specs)) + "]")
            if self.artifact_specs
            else None
        )
        app_specs = (
            ("[" + ", ".join(map(lambda a: str(a), self.app_specs)) + "]")
            if self.app_specs
            else None
        )
        dep_specs = (
            ("[" + ", ".join(map(lambda d: str(d), self.dep_specs)) + "]")
            if self.dep_specs
            else None
        )
        return (
            f'Job(job_id="{self.job_id}", repo_data={self.repo_data}, '
            f'run_name="{self.run_name}", workflow_name={_quoted(self.workflow_name)}, '
            f'provider_name="{self.provider_name}", '
            f"local_repo_user_name={_quoted(self.local_repo_user_name)}, "
            f"local_repo_user_email={_quoted(self.local_repo_user_email)}, "
            f"status=JobStatus.{self.status.name}, "
            f"submitted_at={self.submitted_at}, "
            f'image_name="{self.image_name}", '
            f"commands={commands}, "
            f"env={self.env}, "
            f"working_dir={_quoted(self.working_dir)}, "
            f"port_count={self.port_count}, "
            f"ports={self.ports}, "
            f"host_name={_quoted(self.host_name)}, "
            f"artifact_specs={artifact_specs}, "
            f"requirements={self.requirements}, "
            f"dep_specs={dep_specs}, "
            f"master_job={self.master_job}, "
            f"app_specs={app_specs}, "
            f"runner_id={_quoted(self.runner_id)}, "
            f"request_id={_quoted(self.request_id)}, "
            f"tag_name={_quoted(self.tag_name)})"
        )

    def job_head_key(self, add_prefix=True):
        prefix = ""
        if add_prefix:
            prefix = f"jobs/{self.repo_data.path()}/"
        key = (
            f"{prefix}l;"
            f"{self.job_id};"
            f"{self.provider_name};"
            f"{self.local_repo_user_name or ''};"
            f"{self.submitted_at};"
            f"{self.status.value};"
            f"{','.join([a.artifact_path.replace('/', '_') for a in (self.artifact_specs or [])])};"
            f"{','.join([a.app_name for a in (self.app_specs or [])])};"
            f"{self.tag_name or ''}"
        )
        return key

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
            "repo_branch": self.repo_data.repo_branch,
            "repo_hash": self.repo_data.repo_hash,
            "repo_diff": self.repo_data.repo_diff or "",
            "run_name": self.run_name,
            "workflow_name": self.workflow_name or "",
            "provider_name": self.provider_name,
            "local_repo_user_name": self.local_repo_user_name or "",
            "local_repo_user_email": self.local_repo_user_email or "",
            "status": self.status.value,
            "submitted_at": self.submitted_at,
            "image_name": self.image_name,
            "commands": self.commands or [],
            "env": self.env or {},
            "working_dir": self.working_dir or "",
            "artifacts": artifacts,
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
        }
        return job_data

    @staticmethod
    def unserialize(job_data: dict):
        _requirements = job_data.get("requirements")
        requirements = (
            Requirements(
                _requirements.get("cpus") or None,
                _requirements.get("memory_mib") or None,
                GpusRequirements(
                    _requirements["gpus"].get("count") or None,
                    _requirements["gpus"].get("memory") or None,
                    _requirements["gpus"].get("name") or None,
                )
                if _requirements.get("gpus")
                else None,
                _requirements.get("shm_size_mib") or None,
                _requirements.get("interruptible") or None,
                _requirements.get("local") or None,
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
                    RepoAddress(
                        dep["repo_host_name"],
                        dep.get("repo_port") or None,
                        dep["repo_user_name"],
                        dep["repo_name"],
                    ),
                    dep["run_name"],
                    dep.get("mount") is True,
                )
                dep_specs.append(dep_spec)
        artifact_specs = []
        if job_data.get("artifacts"):
            for artifact in job_data["artifacts"]:
                if isinstance(artifact, str):
                    artifact_spec = ArtifactSpec(artifact, False)
                else:
                    artifact_spec = ArtifactSpec(artifact["path"], artifact.get("mount") is True)
                artifact_specs.append(artifact_spec)
        master_job = JobRefId(job_data["master_job_id"]) if job_data.get("master_job_id") else None
        app_specs = (
            [
                AppSpec(
                    a["port_index"],
                    a["app_name"],
                    a.get("url_path") or None,
                    a.get("url_query_params") or None,
                )
                for a in (job_data.get("apps") or [])
            ]
        ) or None
        job = Job(
            job_data["job_id"],
            RepoData(
                job_data["repo_host_name"],
                job_data.get("repo_port") or None,
                job_data["repo_user_name"],
                job_data["repo_name"],
                job_data["repo_branch"],
                job_data["repo_hash"],
                job_data["repo_diff"] or None,
            ),
            job_data["run_name"],
            job_data.get("workflow_name") or None,
            job_data["provider_name"],
            job_data.get("local_repo_user_name"),
            job_data.get("local_repo_user_email") or None,
            JobStatus(job_data["status"]),
            job_data["submitted_at"],
            job_data["image_name"],
            job_data.get("commands") or None,
            job_data["env"] or None,
            job_data.get("working_dir") or None,
            artifact_specs,
            job_data.get("port_count") or None,
            job_data.get("ports") or None,
            job_data.get("host_name") or None,
            requirements,
            dep_specs or None,
            master_job,
            app_specs,
            job_data.get("runner_id") or None,
            job_data.get("request_id") or None,
            job_data.get("tag_name") or None,
        )
        return job


class JobSpec(JobRef):
    def __init__(
        self,
        image_name: str,
        commands: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
        working_dir: Optional[str] = None,
        artifact_specs: Optional[List[ArtifactSpec]] = None,
        port_count: Optional[int] = None,
        requirements: Optional[Requirements] = None,
        master_job: Optional[JobRef] = None,
        app_specs: Optional[List[AppSpec]] = None,
    ):
        self.job_id = None
        self.image_name = image_name
        self.commands = commands
        self.env = env
        self.working_dir = working_dir
        self.port_count = port_count
        self.artifact_specs = artifact_specs
        self.requirements = requirements
        self.master_job = master_job
        self.app_specs = app_specs

    def get_id(self) -> Optional[str]:
        return self.job_id

    def set_id(self, job_id: Optional[str]):
        self.job_id = job_id

    def __str__(self) -> str:
        commands = (
            ("[" + ", ".join(map(lambda a: _quoted(str(a)), self.commands)) + "]")
            if self.commands
            else None
        )
        artifact_specs = (
            ("[" + ", ".join(map(lambda a: str(a), self.artifact_specs)) + "]")
            if self.artifact_specs
            else None
        )
        app_specs = (
            ("[" + ", ".join(map(lambda a: str(a), self.app_specs)) + "]")
            if self.app_specs
            else None
        )
        return (
            f'JobSpec(job_id="{self.job_id}", image_name="{self.image_name}", '
            f"commands={commands}, "
            f"env={self.env}, "
            f"working_dir={_quoted(self.working_dir)}, "
            f"port_count={self.port_count}, "
            f"artifact_specs={artifact_specs}, "
            f"requirements={self.requirements}, "
            f"master_job={self.master_job}, "
            f"app_specs={app_specs})"
        )
