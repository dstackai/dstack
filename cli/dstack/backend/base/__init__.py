from abc import ABC, abstractmethod
from datetime import datetime
from typing import Generator, List, Optional

from dstack.backend.base import jobs as base_jobs
from dstack.core.artifact import Artifact
from dstack.core.config import BackendConfig
from dstack.core.job import Job, JobHead, JobStatus
from dstack.core.log_event import LogEvent
from dstack.core.repo import RemoteRepoCredentials, Repo, RepoHead
from dstack.core.run import RunHead
from dstack.core.secret import Secret
from dstack.core.tag import TagHead
from dstack.utils.common import PathLike


class Backend(ABC):
    NAME = None

    def __init__(
        self,
        backend_config: BackendConfig,
        repo: Optional[Repo],
    ):
        self.backend_config = backend_config
        self.repo = repo

    @property
    def name(self) -> str:
        return self.NAME

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
        base_jobs.update_job_submission(job)
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

    @abstractmethod
    def list_job_heads(
        self, run_name: Optional[str] = None, repo_id: Optional[str] = None
    ) -> List[JobHead]:
        pass

    @abstractmethod
    def delete_job_head(self, job_id: str, repo_id: Optional[str] = None):
        pass

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
    def list_repo_heads(self) -> List[RepoHead]:
        pass

    @abstractmethod
    def update_repo_last_run_at(self, last_run_at: int):
        pass

    @abstractmethod
    def get_repo_credentials(self) -> Optional[RemoteRepoCredentials]:
        pass

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

    @abstractmethod
    def delete_workflow_cache(self, workflow_name: str):
        pass

    @abstractmethod
    def get_signed_download_url(self, object_key: str) -> str:
        pass

    @abstractmethod
    def get_signed_upload_url(self, object_key: str) -> str:
        pass
