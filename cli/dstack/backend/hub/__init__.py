import sys
from abc import ABC
from pathlib import Path
from typing import Dict, Generator, List, Optional, Tuple

from dstack.backend.base import RemoteBackend, BackendType
from dstack.backend.hub.config import HUBConfig
from dstack.core.error import ConfigError
from dstack.core.artifact import Artifact
from dstack.core.job import Job, JobHead
from dstack.core.log_event import LogEvent
from dstack.core.repo import RepoAddress, RepoCredentials, LocalRepoData, RepoHead
from dstack.core.run import RunHead
from dstack.core.secret import Secret
from dstack.core.tag import TagHead
from dstack.backend.hub.client import HubClient


class HubBackend(RemoteBackend):
    def __init__(self):
        self.backend_config = HUBConfig()
        try:
            self.backend_config.load()
            self._loaded = True
        except ConfigError:
            self._loaded = False

    def _hub_client(self) -> HubClient:
        _client = HubClient(
            host=self.backend_config.host,
            port=self.backend_config.port,
            token=self.backend_config.token,
            hub_name=self.backend_config.hub_name,
        )
        return _client

    @property
    def name(self):
        return "hub"

    @property
    def type(self) -> BackendType:
        return BackendType.REMOTE

    def configure(self):
        pass

    def create_run(self, repo_address: RepoAddress) -> str:
        # /{hub_name}/runs/create
        pass

    def create_job(self, job: Job):
        # /{hub_name}/jobs/create
        pass

    def get_job(self, repo_address: RepoAddress, job_id: str) -> Optional[Job]:
        # /{hub_name}/jobs/get
        pass

    def list_jobs(self, repo_address: RepoAddress, run_name: str) -> List[Job]:
        # /{hub_name}/jobs/list
        pass

    def run_job(self, job: Job):
        # /{hub_name}/runners/run
        pass

    def stop_job(self, repo_address: RepoAddress, job_id: str, abort: bool):
        # /{hub_name}/runners/stop
        pass

    def list_job_heads(self, repo_address: RepoAddress, run_name: Optional[str] = None):
        # /{hub_name}/jobs/list/heads
        pass

    def delete_job_head(self, repo_address: RepoAddress, job_id: str):
        # /{hub_name}/jobs/delete
        pass

    def list_run_heads(
            self,
            repo_address: RepoAddress,
            run_name: Optional[str] = None,
            include_request_heads: bool = True,
    ) -> List[RunHead]:
        job_heads = self.list_job_heads(repo_address, run_name)
        # /{hub_name}/runs/list
        pass

    def poll_logs(
            self,
            repo_address: RepoAddress,
            job_heads: List[JobHead],
            start_time: int,
            attached: bool,
    ) -> Generator[LogEvent, None, None]:
        # /{hub_name}/logs/poll
        pass

    def list_run_artifact_files(
            self, repo_address: RepoAddress, run_name: str
    ) -> Generator[Artifact, None, None]:
        # /{hub_name}/artifacts/list
        pass

    def download_run_artifact_files(
            self,
            repo_address: RepoAddress,
            run_name: str,
            output_dir: Optional[str],
            output_job_dirs: bool = True,
    ):
        # /{hub_name}/artifacts/download
        pass

    def upload_job_artifact_files(
            self,
            repo_address: RepoAddress,
            job_id: str,
            artifact_name: str,
            local_path: Path,
    ):
        # /{hub_name}/artifacts/upload
        pass

    def list_tag_heads(self, repo_address: RepoAddress) -> List[TagHead]:
        # /{hub_name}/tags/list/heads
        pass

    def get_tag_head(self, repo_address: RepoAddress, tag_name: str) -> Optional[TagHead]:
        # /{hub_name}/tags/get
        pass

    def add_tag_from_run(
            self,
            repo_address: RepoAddress,
            tag_name: str,
            run_name: str,
            run_jobs: Optional[List[Job]],
    ):
        # /{hub_name}/tags/add
        pass

    def add_tag_from_local_dirs(
            self, repo_data: LocalRepoData, tag_name: str, local_dirs: List[str]
    ):
        # /{hub_name}/tags/add
        pass

    def delete_tag_head(self, repo_address: RepoAddress, tag_head: TagHead):
        # /{hub_name}/tags/delete
        pass

    def update_repo_last_run_at(self, repo_address: RepoAddress, last_run_at: int):
        # /{hub_name}/repos/update
        pass

    def get_repo_credentials(self, repo_address: RepoAddress) -> Optional[RepoCredentials]:
        return self._hub_client().get_repos_credentials(repo_address=repo_address)

    def save_repo_credentials(self, repo_address: RepoAddress, repo_credentials: RepoCredentials):
        self._hub_client().save_repos_credentials(
            repo_address=repo_address,
            repo_credentials=repo_credentials
        )

    def list_secret_names(self, repo_address: RepoAddress) -> List[str]:
        # /{hub_name}/secrets/list
        pass

    def get_secret(self, repo_address: RepoAddress, secret_name: str) -> Optional[Secret]:
        # /{hub_name}/secrets/get
        pass

    def add_secret(self, repo_address: RepoAddress, secret: Secret):
        # /{hub_name}/secrets/add
        pass

    def update_secret(self, repo_address: RepoAddress, secret: Secret):
        # /{hub_name}/secrets/update
        pass

    def delete_secret(self, repo_address: RepoAddress, secret_name: str):
        # /{hub_name}/secrets/delete
        pass
