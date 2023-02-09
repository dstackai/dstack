import sys
from pathlib import Path
from typing import Dict, Generator, List, Optional, Tuple

from dstack.backend.base import Backend, BackendType
from dstack.backend.base import jobs as base_jobs
from dstack.backend.base import repos as base_repos
from dstack.backend.base import runs as base_runs
from dstack.backend.base import secrets as base_secrets
from dstack.backend.base import tags as base_tags
from dstack.backend.local import artifacts, jobs, logs, repos, runners, runs, secrets, tags
from dstack.backend.local.compute import LocalCompute
from dstack.backend.local.config import LocalConfig
from dstack.backend.local.storage import LocalStorage
from dstack.core.artifact import Artifact
from dstack.core.job import Job, JobHead
from dstack.core.log_event import LogEvent
from dstack.core.repo import RepoAddress, RepoCredentials, RepoData, RepoHead
from dstack.core.run import RunHead
from dstack.core.secret import Secret
from dstack.core.tag import TagHead


class LocalBackend(Backend):
    def __init__(self):
        self.backend_config = LocalConfig()
        self.backend_config.load()
        self._loaded = True
        self._storage = LocalStorage(self.backend_config.path)
        self._compute = LocalCompute()

    @property
    def name(self):
        return "local"

    @property
    def type(self) -> BackendType:
        return BackendType.LOCAL

    def configure(self):
        pass

    def create_run(self, repo_address: RepoAddress) -> str:
        return base_runs.create_run(self._storage, repo_address, self.type)

    def create_job(self, job: Job):
        base_jobs.create_job(self._storage, job)

    def get_job(self, repo_address: RepoAddress, job_id: str) -> Optional[Job]:
        return base_jobs.get_job(self._storage, repo_address, job_id)

    def list_jobs(self, repo_address: RepoAddress, run_name: str) -> List[Job]:
        return base_jobs.list_jobs(self._storage, repo_address, run_name)

    def run_job(self, job: Job):
        base_jobs.run_job(self._storage, self._compute, job)

    def stop_job(self, repo_address: RepoAddress, job_id: str, abort: bool):
        base_jobs.stop_job(self._storage, self._compute, repo_address, job_id, abort)

    def list_job_heads(
        self, repo_address: RepoAddress, run_name: Optional[str] = None
    ) -> List[JobHead]:
        return base_jobs.list_job_heads(self._storage, repo_address, run_name)

    def delete_job_head(self, repo_address: RepoAddress, job_id: str):
        base_jobs.delete_job_head(self._storage, repo_address, job_id)

    def list_run_heads(
        self,
        repo_address: RepoAddress,
        run_name: Optional[str] = None,
        include_request_heads: bool = True,
    ) -> List[RunHead]:
        job_heads = self.list_job_heads(repo_address, run_name)
        return base_runs.get_run_heads(
            self._storage, self._compute, job_heads, include_request_heads
        )

    def poll_logs(
        self,
        repo_address: RepoAddress,
        job_heads: List[JobHead],
        start_time: int,
        attached: bool,
    ) -> Generator[LogEvent, None, None]:
        return logs.poll_logs(
            self.backend_config.path, repo_address, job_heads, start_time, attached
        )

    def list_run_artifact_files(
        self, repo_address: RepoAddress, run_name: str
    ) -> Generator[Artifact, None, None]:
        return artifacts.list_run_artifact_files(self.backend_config.path, repo_address, run_name)

    def list_tag_heads(self, repo_address: RepoAddress) -> List[TagHead]:
        return base_tags.list_tag_heads(self._storage, repo_address)

    def get_tag_head(self, repo_address: RepoAddress, tag_name: str) -> Optional[TagHead]:
        return base_tags.get_tag_head(self._storage, repo_address, tag_name)

    def add_tag_from_run(
        self,
        repo_address: RepoAddress,
        tag_name: str,
        run_name: str,
        run_jobs: Optional[List[Job]],
    ):
        base_tags.create_tag_from_run(
            self._storage,
            repo_address,
            tag_name,
            run_name,
            run_jobs,
        )

    def add_tag_from_local_dirs(self, repo_data: RepoData, tag_name: str, local_dirs: List[str]):
        tags.create_tag_from_local_dirs(
            self.backend_config.path,
            repo_data,
            tag_name,
            local_dirs,
        )

    def delete_tag_head(self, repo_address: RepoAddress, tag_head: TagHead):
        base_tags.delete_tag(self._storage, repo_address, tag_head)

    def update_repo_last_run_at(self, repo_address: RepoAddress, last_run_at: int):
        base_repos.update_repo_last_run_at(
            self._storage,
            repo_address,
            last_run_at,
        )

    def get_repo_credentials(self, repo_address: RepoAddress) -> Optional[RepoCredentials]:
        return repos.get_repo_credentials(self.backend_config.path, repo_address)

    def save_repo_credentials(self, repo_address: RepoAddress, repo_credentials: RepoCredentials):
        repos.save_repo_credentials(self.backend_config.path, repo_address, repo_credentials)

    def list_secret_names(self, repo_address: RepoAddress) -> List[str]:
        return secrets.list_secret_names(self.backend_config.path, repo_address)

    def get_secret(self, repo_address: RepoAddress, secret_name: str) -> Optional[Secret]:
        return secrets.get_secret(self.backend_config.path, repo_address, secret_name)

    def add_secret(self, repo_address: RepoAddress, secret: Secret):
        return secrets.add_secret(self.backend_config.path, repo_address, secret)

    def update_secret(self, repo_address: RepoAddress, secret: Secret):
        return secrets.update_secret(self.backend_config.path, repo_address, secret)

    def delete_secret(self, repo_address: RepoAddress, secret_name: str):
        return secrets.remove_secret(self.backend_config.path, repo_address, secret_name)

    def get_artifacts_path(self, repo_address: RepoAddress) -> Path:
        return artifacts.get_artifacts_path(self.backend_config.path, repo_address)
