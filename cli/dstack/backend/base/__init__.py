from abc import ABC, abstractmethod
from datetime import datetime
from typing import Generator, List, Optional

from dstack.backend.base import jobs as base_jobs
from dstack.backend.base.compute import Compute
from dstack.backend.base.config import BackendConfig
from dstack.backend.base.secrets import SecretsManager
from dstack.backend.base.storage import Storage
from dstack.core.artifact import Artifact
from dstack.core.job import Job, JobHead, JobStatus
from dstack.core.log_event import LogEvent
from dstack.core.repo import RemoteRepoCredentials, RepoHead, RepoSpec
from dstack.core.run import RunHead
from dstack.core.secret import Secret
from dstack.core.tag import TagHead
from dstack.utils.common import PathLike


class Backend(ABC):
    NAME = None
    backend_config: BackendConfig
    _storage: Storage
    _compute: Compute
    _secrets_manager: SecretsManager

    def __init__(
        self,
        backend_config: BackendConfig,
    ):
        self.backend_config = backend_config

    @property
    def name(self) -> str:
        return self.NAME

    @abstractmethod
    def create_run(self, repo_id: str) -> str:
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
    def get_job(self, repo_id: str, job_id: str) -> Optional[Job]:
        pass

    @abstractmethod
    def list_jobs(self, repo_id: str, run_name: str) -> List[Job]:
        pass

    @abstractmethod
    def run_job(self, job: Job, failed_to_start_job_new_status: JobStatus):
        pass

    @abstractmethod
    def stop_job(self, repo_id: str, abort: bool, job_id: str):
        pass

    @abstractmethod
    def list_job_heads(self, repo_id: str, run_name: Optional[str] = None) -> List[JobHead]:
        pass

    @abstractmethod
    def delete_job_head(self, repo_id: str, job_id: str):
        pass

    @abstractmethod
    def list_run_heads(
        self,
        repo_id: str,
        run_name: Optional[str] = None,
        include_request_heads: bool = True,
        interrupted_job_new_status: JobStatus = JobStatus.FAILED,
    ) -> List[RunHead]:
        pass

    def get_run_head(
        self,
        repo_id: str,
        run_name: str,
        include_request_heads: bool = True,
        interrupted_job_new_status: JobStatus = JobStatus.FAILED,
    ) -> Optional[RunHead]:
        run_heads_list = self.list_run_heads(
            repo_id=repo_id,
            run_name=run_name,
            include_request_heads=include_request_heads,
            interrupted_job_new_status=interrupted_job_new_status,
        )
        if len(run_heads_list) == 0:
            return None
        return run_heads_list[0]

    @abstractmethod
    def poll_logs(
        self,
        repo_id: str,
        run_name: str,
        start_time: datetime,
        end_time: Optional[datetime] = None,
        descending: bool = False,
    ) -> Generator[LogEvent, None, None]:
        pass

    @abstractmethod
    def list_run_artifact_files(
        self, repo_id: str, run_name: str, prefix: str, recursive: bool = False
    ) -> List[Artifact]:
        pass

    @abstractmethod
    def download_run_artifact_files(
        self,
        repo_id: str,
        run_name: str,
        output_dir: Optional[PathLike],
        files_path: Optional[PathLike] = None,
    ):
        pass

    @abstractmethod
    def upload_job_artifact_files(
        self,
        repo_id: str,
        job_id: str,
        artifact_name: str,
        artifact_path: PathLike,
        local_path: PathLike,
    ):
        pass

    @abstractmethod
    def list_tag_heads(self, repo_id: str) -> List[TagHead]:
        pass

    @abstractmethod
    def get_tag_head(self, repo_id: str, tag_name: str) -> Optional[TagHead]:
        pass

    @abstractmethod
    def add_tag_from_run(
        self, repo_id: str, tag_name: str, run_name: str, run_jobs: Optional[List[Job]]
    ):
        pass

    @abstractmethod
    def add_tag_from_local_dirs(self, tag_name: str, local_dirs: List[str]):
        pass

    @abstractmethod
    def delete_tag_head(self, repo_id: str, tag_head: TagHead):
        pass

    @abstractmethod
    def list_repo_heads(self) -> List[RepoHead]:
        pass

    @abstractmethod
    def update_repo_last_run_at(self, repo_spec: RepoSpec, last_run_at: int):
        pass

    @abstractmethod
    def get_repo_credentials(self, repo_id: str) -> Optional[RemoteRepoCredentials]:
        pass

    @abstractmethod
    def save_repo_credentials(self, repo_id: str, repo_credentials: RemoteRepoCredentials):
        pass

    @abstractmethod
    def list_secret_names(self, repo_id: str) -> List[str]:
        pass

    @abstractmethod
    def get_secret(self, repo_id: str, secret_name: str) -> Optional[Secret]:
        pass

    @abstractmethod
    def add_secret(self, repo_id: str, secret: Secret):
        pass

    @abstractmethod
    def update_secret(self, repo_id: str, secret: Secret):
        pass

    @abstractmethod
    def delete_secret(self, repo_id: str, secret_name: str):
        pass

    @abstractmethod
    def delete_workflow_cache(self, repo_id: str, hub_user_name: str, workflow_name: str):
        pass

    @abstractmethod
    def get_signed_download_url(self, object_key: str) -> str:
        pass

    @abstractmethod
    def get_signed_upload_url(self, object_key: str) -> str:
        pass
