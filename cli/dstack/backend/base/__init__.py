import sys
from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import Any, Generator, List, Optional

from dstack.api.repos import get_local_repo_credentials
from dstack.backend.base import jobs
from dstack.core.artifact import Artifact
from dstack.core.config import BackendConfig, Configurator
from dstack.core.job import Job, JobHead, JobStatus
from dstack.core.log_event import LogEvent
from dstack.core.repo import RemoteRepo, RemoteRepoCredentials, Repo, RepoHead
from dstack.core.run import RunHead
from dstack.core.secret import Secret
from dstack.core.tag import TagHead
from dstack.utils.common import PathLike


class BackendType(Enum):
    REMOTE = "remote"
    LOCAL = "local"

    def __str__(self):
        return str(self.value)


class Backend(ABC):
    _loaded = False

    def __init__(
        self,
        repo: Optional[Repo],
        credentials: Optional[RemoteRepoCredentials] = None,
        auto_init: bool = False,
    ):
        self.repo = repo
        self._credentials = credentials
        self._auto_init = auto_init

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
    def create_run(self) -> str:
        pass

    @abstractmethod
    def create_job(self, job: Job):
        pass

    def submit_job(self, job: Job, failed_to_start_job_new_status: JobStatus = JobStatus.FAILED):
        self.create_job(job)
        self.run_job(job, failed_to_start_job_new_status)

    def resubmit_job(self, job: Job, failed_to_start_job_new_status: JobStatus = JobStatus.FAILED):
        jobs.update_job_submission(job)
        self.run_job(job, failed_to_start_job_new_status)

    @abstractmethod
    def get_job(self, job_id: str, repo_id: Optional[str] = None) -> Optional[Job]:
        pass

    @abstractmethod
    def list_jobs(self, run_name: str, repo_id: Optional[str] = None) -> List[Job]:
        pass

    @abstractmethod
    def run_job(self, job: Job, failed_to_start_job_new_status: JobStatus):
        pass

    @abstractmethod
    def stop_job(self, job_id: str, abort: bool):
        pass

    def stop_jobs(self, run_name: Optional[str], abort: bool):
        job_heads = self.list_job_heads(run_name)
        for job_head in job_heads:
            if job_head.status.is_unfinished():
                self.stop_job(job_head.job_id, abort)

    @abstractmethod
    def list_job_heads(
        self, run_name: Optional[str] = None, repo_id: Optional[str] = None
    ) -> List[JobHead]:
        pass

    @abstractmethod
    def delete_job_head(self, job_id: str, repo_id: Optional[str] = None):
        pass

    def delete_job_heads(self, run_name: Optional[str]):
        job_heads = []
        for job_head in self.list_job_heads(run_name):
            if job_head.status.is_finished():
                job_heads.append(job_head)
            else:
                if run_name:
                    sys.exit("The run is not finished yet. Stop the run first.")
        for job_head in job_heads:
            self.delete_job_head(job_head.job_id)

    @abstractmethod
    def list_run_heads(
        self,
        run_name: Optional[str] = None,
        include_request_heads: bool = True,
        interrupted_job_new_status: JobStatus = JobStatus.FAILED,
        repo_id: Optional[str] = None,
    ) -> List[RunHead]:
        pass

    @abstractmethod
    def poll_logs(
        self,
        run_name: str,
        start_time: datetime,
        end_time: Optional[datetime] = None,
        descending: bool = False,
        repo_id: Optional[str] = None,
    ) -> Generator[LogEvent, None, None]:
        pass

    @abstractmethod
    def list_run_artifact_files(
        self, run_name: str, repo_id: Optional[str] = None
    ) -> List[Artifact]:
        # TODO: add a flag for non-recursive listing.
        # Backends may implement this via list_run_artifact_files_and_folders()
        pass

    @abstractmethod
    def download_run_artifact_files(
        self,
        run_name: str,
        output_dir: Optional[PathLike],
        files_path: Optional[PathLike] = None,
    ):
        pass

    @abstractmethod
    def upload_job_artifact_files(
        self,
        job_id: str,
        artifact_name: str,
        artifact_path: PathLike,
        local_path: PathLike,
    ):
        pass

    @abstractmethod
    def list_tag_heads(self) -> List[TagHead]:
        pass

    @abstractmethod
    def get_tag_head(self, tag_name: str) -> Optional[TagHead]:
        pass

    @abstractmethod
    def add_tag_from_run(
        self,
        tag_name: str,
        run_name: str,
        run_jobs: Optional[List[Job]],
    ):
        pass

    @abstractmethod
    def add_tag_from_local_dirs(self, tag_name: str, local_dirs: List[str]):
        pass

    @abstractmethod
    def delete_tag_head(self, tag_head: TagHead):
        pass

    @abstractmethod
    def update_repo_last_run_at(self, last_run_at: int):
        pass

    @abstractmethod
    def _get_repo_credentials(self) -> Optional[RemoteRepoCredentials]:
        pass

    def get_repo_credentials(self) -> Optional[RemoteRepoCredentials]:
        credentials = self._get_repo_credentials()
        if credentials is None:
            if not self._auto_init:
                return None  # todo raise?
            elif self._credentials is not None:
                credentials = self._credentials
            else:
                if isinstance(self.repo, RemoteRepo):
                    credentials = get_local_repo_credentials(self.repo.repo_data)
            self.save_repo_credentials(credentials)
        return credentials

    @abstractmethod
    def save_repo_credentials(self, repo_credentials: RemoteRepoCredentials):
        pass

    @abstractmethod
    def list_secret_names(self) -> List[str]:
        pass

    @abstractmethod
    def get_secret(self, secret_name: str) -> Optional[Secret]:
        pass

    @abstractmethod
    def add_secret(self, secret: Secret):
        pass

    @abstractmethod
    def update_secret(self, secret: Secret):
        pass

    @abstractmethod
    def delete_secret(self, secret_name: str):
        pass

    @classmethod
    @abstractmethod
    def get_configurator(cls) -> Configurator:
        pass

    @abstractmethod
    def delete_workflow_cache(self, workflow_name: str):
        pass


class RemoteBackend(Backend):
    def __init__(
        self,
        backend_config: Optional[BackendConfig] = None,
        repo: Optional[Repo] = None,
        custom_client: Any = None,
        credentials: Optional[RemoteRepoCredentials] = None,
        auto_init: bool = False,
    ):
        super().__init__(repo=repo, credentials=credentials, auto_init=auto_init)

    @abstractmethod
    def list_repo_heads(self) -> List[RepoHead]:
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
