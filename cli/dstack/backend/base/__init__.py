import sys
from abc import ABC, abstractmethod
from enum import Enum
from pathlib import Path
from typing import Generator, List, Optional

from dstack.core.artifact import Artifact
from dstack.core.config import BackendConfig
from dstack.core.job import Job, JobHead
from dstack.core.log_event import LogEvent
from dstack.core.repo import LocalRepoData, RepoAddress, RepoCredentials
from dstack.core.run import RunHead
from dstack.core.runners import Runner
from dstack.core.secret import Secret
from dstack.core.tag import TagHead


class BackendType(Enum):
    REMOTE = "remote"
    LOCAL = "local"

    def __str__(self):
        return str(self.value)


class Backend(ABC):
    _loaded = False

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @property
    @abstractmethod
    def type(self) -> BackendType:
        pass

    @property
    def loaded(self):
        return self._loaded

    @abstractmethod
    def configure(self):
        pass

    @abstractmethod
    def create_run(self, repo_address: RepoAddress) -> str:
        pass

    @abstractmethod
    def create_job(self, job: Job):
        pass

    def submit_job(self, job: Job):
        self.create_job(job)
        self.run_job(job)

    @abstractmethod
    def get_job(self, repo_address: RepoAddress, job_id: str) -> Optional[Job]:
        pass

    @abstractmethod
    def list_jobs(self, repo_address: RepoAddress, run_name: str) -> List[Job]:
        pass

    @abstractmethod
    def run_job(self, job: Job) -> Runner:
        pass

    @abstractmethod
    def stop_job(self, repo_address: RepoAddress, job_id: str, abort: bool):
        pass

    def stop_jobs(self, repo_address: RepoAddress, run_name: Optional[str], abort: bool):
        job_heads = self.list_job_heads(repo_address, run_name)
        for job_head in job_heads:
            if job_head.status.is_unfinished():
                self.stop_job(repo_address, job_head.job_id, abort)

    @abstractmethod
    def list_job_heads(
        self, repo_address: RepoAddress, run_name: Optional[str] = None
    ) -> List[JobHead]:
        pass

    @abstractmethod
    def delete_job_head(self, repo_address: RepoAddress, job_id: str):
        pass

    def delete_job_heads(self, repo_address: RepoAddress, run_name: Optional[str]):
        job_heads = []
        for job_head in self.list_job_heads(repo_address, run_name):
            if job_head.status.is_finished():
                job_heads.append(job_head)
            else:
                if run_name:
                    sys.exit("The run is not finished yet. Stop the run first.")
        for job_head in job_heads:
            self.delete_job_head(repo_address, job_head.job_id)

    @abstractmethod
    def list_run_heads(
        self,
        repo_address: RepoAddress,
        run_name: Optional[str] = None,
        include_request_heads: bool = True,
    ) -> List[RunHead]:
        pass

    @abstractmethod
    def poll_logs(
        self,
        repo_address: RepoAddress,
        job_heads: List[JobHead],
        start_time: int,
        attached: bool,
    ) -> Generator[LogEvent, None, None]:
        pass

    @abstractmethod
    def list_run_artifact_files(self, repo_address: RepoAddress, run_name: str) -> List[Artifact]:
        # TODO: add a flag for non-recursive listing.
        # Backends may implement this via list_run_artifact_files_and_folders()
        pass

    @abstractmethod
    def download_run_artifact_files(
        self,
        repo_address: RepoAddress,
        run_name: str,
        output_dir: Optional[str],
    ):
        pass

    @abstractmethod
    def upload_job_artifact_files(
        self,
        repo_address: RepoAddress,
        job_id: str,
        artifact_name: str,
        artifact_path: str,
        local_path: Path,
    ):
        pass

    @abstractmethod
    def list_tag_heads(self, repo_address: RepoAddress) -> List[TagHead]:
        pass

    @abstractmethod
    def get_tag_head(self, repo_address: RepoAddress, tag_name: str) -> Optional[TagHead]:
        pass

    @abstractmethod
    def add_tag_from_run(
        self,
        repo_address: RepoAddress,
        tag_name: str,
        run_name: str,
        run_jobs: Optional[List[Job]],
    ):
        pass

    @abstractmethod
    def add_tag_from_local_dirs(
        self, repo_data: LocalRepoData, tag_name: str, local_dirs: List[str]
    ):
        pass

    @abstractmethod
    def delete_tag_head(self, repo_address: RepoAddress, tag_head: TagHead):
        pass

    @abstractmethod
    def update_repo_last_run_at(self, repo_address: RepoAddress, last_run_at: int):
        pass

    @abstractmethod
    def get_repo_credentials(self, repo_address: RepoAddress) -> Optional[RepoCredentials]:
        pass

    @abstractmethod
    def save_repo_credentials(self, repo_address: RepoAddress, repo_credentials: RepoCredentials):
        pass

    @abstractmethod
    def list_secret_names(self, repo_address: RepoAddress) -> List[str]:
        pass

    @abstractmethod
    def get_secret(self, repo_address: RepoAddress, secret_name: str) -> Optional[Secret]:
        pass

    @abstractmethod
    def add_secret(self, repo_address: RepoAddress, secret: Secret):
        pass

    @abstractmethod
    def update_secret(self, repo_address: RepoAddress, secret: Secret):
        pass

    @abstractmethod
    def delete_secret(self, repo_address: RepoAddress, secret_name: str):
        pass


class RemoteBackend(Backend):
    def __init__(self, backend_config: Optional[BackendConfig] = None):
        pass

    @property
    def type(self) -> BackendType:
        return BackendType.REMOTE


class CloudBackend(RemoteBackend):
    @abstractmethod
    def get_signed_download_url(self, object_key: str) -> str:
        pass

    @abstractmethod
    def get_signed_upload_url(self, object_key: str) -> str:
        pass
