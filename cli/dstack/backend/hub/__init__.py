import sys
from abc import ABC
from pathlib import Path
from typing import Dict, Generator, List, Optional, Tuple

from dstack.backend.base import BackendType, RemoteBackend
from dstack.backend.base import artifacts as base_artifacts
from dstack.backend.hub.client import HubClient
from dstack.backend.hub.config import HUBConfig, HubConfigurator
from dstack.backend.hub.storage import HUBStorage
from dstack.core.artifact import Artifact
from dstack.core.config import BackendConfig
from dstack.core.error import ConfigError
from dstack.core.job import Job, JobHead, JobStatus
from dstack.core.log_event import LogEvent
from dstack.core.repo import LocalRepoData, RepoAddress, RepoCredentials, RepoHead
from dstack.core.run import RunHead
from dstack.core.secret import Secret
from dstack.core.tag import TagHead


class HubBackend(RemoteBackend):
    _client = None
    _storage = None

    def __init__(self, config: Optional[BackendConfig] = None):
        super().__init__(config)
        self.backend_config = HUBConfig()
        try:
            self.backend_config.load()
            self._loaded = True
            self._storage = HUBStorage(self._hub_client())
        except ConfigError:
            self._loaded = False

    def _hub_client(self) -> HubClient:
        if self._client is None:
            self._client = HubClient(
                url=self.backend_config.url,
                project=self.backend_config.project,
                token=self.backend_config.token,
            )
        return self._client

    @property
    def name(self):
        return "hub"

    @property
    def type(self) -> BackendType:
        return BackendType.REMOTE

    def configure(self):
        pass

    def create_run(self, repo_address: RepoAddress) -> str:
        return self._hub_client().create_run(repo_address=repo_address)

    def create_job(self, job: Job):
        self._hub_client().create_job(job=job)

    def get_job(self, repo_address: RepoAddress, job_id: str) -> Optional[Job]:
        return self._hub_client().get_job(repo_address=repo_address, job_id=job_id)

    def list_jobs(self, repo_address: RepoAddress, run_name: str) -> List[Job]:
        return self._hub_client().list_jobs(repo_address=repo_address, run_name=run_name)

    def run_job(self, job: Job, failed_to_start_job_new_status: JobStatus):
        self._hub_client().run_job(job=job)

    def stop_job(self, repo_address: RepoAddress, job_id: str, abort: bool):
        self._hub_client().stop_job(repo_address=repo_address, job_id=job_id, abort=abort)

    def list_job_heads(
        self, repo_address: RepoAddress, run_name: Optional[str] = None
    ) -> List[JobHead]:
        return self._hub_client().list_job_heads(repo_address=repo_address, run_name=run_name)

    def delete_job_head(self, repo_address: RepoAddress, job_id: str):
        self._hub_client().delete_job_head(repo_address=repo_address, job_id=job_id)

    def list_run_heads(
        self,
        repo_address: RepoAddress,
        run_name: Optional[str] = None,
        include_request_heads: bool = True,
        interrupted_job_new_status: JobStatus = JobStatus.FAILED,
    ) -> List[RunHead]:
        return self._hub_client().list_run_heads(
            repo_address=repo_address,
            run_name=run_name,
            include_request_heads=include_request_heads,
        )

    def poll_logs(
        self,
        repo_address: RepoAddress,
        job_heads: List[JobHead],
        start_time: int,
        attached: bool,
    ) -> Generator[LogEvent, None, None]:
        # /{hub_name}/logs/poll
        return self._hub_client().poll_logs(
            repo_address=repo_address,
            job_heads=job_heads,
            start_time=start_time,
            attached=attached,
        )

    def list_run_artifact_files(self, repo_address: RepoAddress, run_name: str) -> List[Artifact]:
        # /{hub_name}/artifacts/list
        return self._hub_client().list_run_artifact_files(
            repo_address=repo_address, run_name=run_name
        )

    def download_run_artifact_files(
        self,
        repo_address: RepoAddress,
        run_name: str,
        output_dir: Optional[str],
        files_path: Optional[str] = None,
    ):
        # /{hub_name}/artifacts/download
        artifacts = self.list_run_artifact_files(repo_address=repo_address, run_name=run_name)
        base_artifacts.download_run_artifact_files(
            storage=self._storage,
            repo_address=repo_address,
            artifacts=artifacts,
            output_dir=output_dir,
            files_path=files_path,
        )

    def upload_job_artifact_files(
        self,
        repo_address: RepoAddress,
        job_id: str,
        artifact_name: str,
        artifact_path: str,
        local_path: Path,
    ):
        # /{hub_name}/artifacts/upload
        base_artifacts.upload_job_artifact_files(
            storage=self._storage,
            repo_address=repo_address,
            job_id=job_id,
            artifact_name=artifact_name,
            artifact_path=artifact_path,
            local_path=local_path,
        )

    def list_tag_heads(self, repo_address: RepoAddress) -> List[TagHead]:
        return self._hub_client().list_tag_heads(repo_address=repo_address)

    def get_tag_head(self, repo_address: RepoAddress, tag_name: str) -> Optional[TagHead]:
        return self._hub_client().get_tag_head(repo_address=repo_address, tag_name=tag_name)

    def add_tag_from_run(
        self,
        repo_address: RepoAddress,
        tag_name: str,
        run_name: str,
        run_jobs: Optional[List[Job]],
    ):
        return self._hub_client().add_tag_from_run(
            repo_address=repo_address, tag_name=tag_name, run_name=run_name, run_jobs=run_jobs
        )

    def add_tag_from_local_dirs(
        self, repo_data: LocalRepoData, tag_name: str, local_dirs: List[str]
    ):
        # /{hub_name}/tags/add
        return self._hub_client().add_tag_from_local_dirs(
            repo_data=repo_data, tag_name=tag_name, local_dirs=local_dirs
        )

    def delete_tag_head(self, repo_address: RepoAddress, tag_head: TagHead):
        # /{hub_name}/tags/delete
        return self._hub_client().delete_tag_head(repo_address=repo_address, tag_head=tag_head)

    def update_repo_last_run_at(self, repo_address: RepoAddress, last_run_at: int):
        # /{hub_name}/repos/update
        return self._hub_client().update_repo_last_run_at(
            repo_address=repo_address, last_run_at=last_run_at
        )

    def get_repo_credentials(self, repo_address: RepoAddress) -> Optional[RepoCredentials]:
        return self._hub_client().get_repos_credentials(repo_address=repo_address)

    def save_repo_credentials(self, repo_address: RepoAddress, repo_credentials: RepoCredentials):
        self._hub_client().save_repos_credentials(
            repo_address=repo_address, repo_credentials=repo_credentials
        )

    def list_secret_names(self, repo_address: RepoAddress) -> List[str]:
        return self._hub_client().list_secret_names(repo_address=repo_address)

    def get_secret(self, repo_address: RepoAddress, secret_name: str) -> Optional[Secret]:
        return self._hub_client().get_secret(repo_address=repo_address, secret_name=secret_name)

    def add_secret(self, repo_address: RepoAddress, secret: Secret):
        self._hub_client().add_secret(repo_address=repo_address, secret=secret)

    def update_secret(self, repo_address: RepoAddress, secret: Secret):
        self._hub_client().update_secret(repo_address=repo_address, secret=secret)

    def delete_secret(self, repo_address: RepoAddress, secret_name: str):
        # /{hub_name}/secrets/delete
        self._hub_client().delete_secret(repo_address=repo_address, secret_name=secret_name)

    def get_configurator(self):
        return HubConfigurator()

    def delete_workflow_cache(self, repo_address: RepoAddress, username: str, workflow_name: str):
        self._hub_client().delete_workflow_cache(
            repo_address=repo_address, username=username, workflow_name=workflow_name
        )
