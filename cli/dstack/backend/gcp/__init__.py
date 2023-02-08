import uuid
from pathlib import Path
from typing import Generator, List, Optional

from dstack.backend.base import RemoteBackend
from dstack.backend.gcp import jobs, runs, storage
from dstack.backend.gcp.config import GCPConfig
from dstack.core.artifact import Artifact
from dstack.core.job import Job, JobHead
from dstack.core.log_event import LogEvent
from dstack.core.repo import (
    LocalRepoData,
    RepoAddress,
    RepoCredentials,
    RepoData,
    RepoHead,
    RepoProtocol,
)
from dstack.core.run import RunHead
from dstack.core.runners import Runner
from dstack.core.secret import Secret
from dstack.core.tag import TagHead


class GCPBackend(RemoteBackend):
    def __init__(self):
        self.config = GCPConfig()
        self._storage_client = storage.get_client(project_id=self.config.project_id)
        self.configure()
        self._loaded = True

    @property
    def name(self) -> str:
        "gcp"

    def configure(self):
        self._bucket = storage.get_or_create_bucket(self._storage_client, self.config.bucket_name)

    def create_run(self, repo_address: RepoAddress) -> str:
        return runs.create_run(self._bucket)

    def submit_job(self, job: Job, counter: List[int]):
        job.runner_id = uuid.uuid4().hex
        jobs.create_job(self._bucket, job)
        jobs.run_job(self.config, self._bucket, job)

    def get_job(self, repo_address: RepoAddress, job_id: str) -> Optional[Job]:
        return jobs.get_job(self._bucket, repo_address, job_id)

    def list_job_heads(
        self, repo_address: RepoAddress, run_name: Optional[str] = None
    ) -> List[JobHead]:
        return jobs.list_job_heads(self._bucket, repo_address, run_name)

    def list_jobs(self, repo_address: RepoAddress, run_name: str) -> List[Job]:
        raise NotImplementedError()

    def run_job(self, job: Job) -> Runner:
        raise NotImplementedError()

    def stop_job(self, repo_address: RepoAddress, job_id: str, abort: bool):
        jobs.stop_job(self.config, self._bucket, repo_address, job_id, abort)

    def delete_job_head(self, repo_address: RepoAddress, job_id: str):
        jobs.delete_job_head(self._bucket, repo_address, job_id)

    def store_job(self, job: Job):
        raise NotImplementedError()

    def get_run_heads(
        self,
        repo_address: RepoAddress,
        job_heads: List[JobHead],
        include_request_heads: bool = True,
    ) -> List[RunHead]:
        return runs.get_run_heads(self._bucket, repo_address, job_heads, include_request_heads)

    def poll_logs(
        self,
        repo_address: RepoAddress,
        job_heads: List[JobHead],
        start_time: int,
        attached: bool,
    ) -> Generator[LogEvent, None, None]:
        pass

    def list_run_artifact_files(
        self, repo_address: RepoAddress, run_name: str
    ) -> Generator[Artifact, None, None]:
        # TODO: add a flag for non-recursive listing.
        # Backends may implement this via list_run_artifact_files_and_folders()
        pass

    def list_tag_heads(self, repo_address: RepoAddress) -> List[TagHead]:
        pass

    def get_tag_head(self, repo_address: RepoAddress, tag_name: str) -> Optional[TagHead]:
        pass

    def add_tag_from_run(
        self,
        repo_address: RepoAddress,
        tag_name: str,
        run_name: str,
        run_jobs: Optional[List[Job]],
    ):
        pass

    def add_tag_from_local_dirs(self, repo_data: RepoData, tag_name: str, local_dirs: List[str]):
        pass

    def delete_tag_head(self, repo_address: RepoAddress, tag_head: TagHead):
        pass

    def list_repo_heads(self) -> List[RepoHead]:
        pass

    def update_repo_last_run_at(self, repo_address: RepoAddress, last_run_at: int):
        pass

    def increment_repo_tags_count(self, repo_address: RepoAddress):
        pass

    def decrement_repo_tags_count(self, repo_address: RepoAddress):
        pass

    def delete_repo(self, repo_address: RepoAddress):
        pass

    def get_repo_credentials(self, repo_address: RepoAddress) -> Optional[RepoCredentials]:
        pass

    def save_repo_credentials(self, repo_address: RepoAddress, repo_credentials: RepoCredentials):
        pass

    def list_secret_names(self, repo_address: RepoAddress) -> List[str]:
        pass

    def get_secret(self, repo_address: RepoAddress, secret_name: str) -> Optional[Secret]:
        pass

    def add_secret(self, repo_address: RepoAddress, secret: Secret):
        pass

    def update_secret(self, repo_address: RepoAddress, secret: Secret):
        pass

    def delete_secret(self, repo_address: RepoAddress, secret_name: str):
        pass

    def download_run_artifact_files(
        self,
        repo_address: RepoAddress,
        run_name: str,
        output_dir: Optional[str],
        output_job_dirs: bool = True,
    ):
        pass

    def upload_job_artifact_files(
        self,
        repo_address: RepoAddress,
        job_id: str,
        artifact_name: str,
        local_path: Path,
    ):
        pass
