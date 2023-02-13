import warnings
from pathlib import Path
from typing import Generator, List, Optional

from google.auth._default import _CLOUD_SDK_CREDENTIALS_WARNING

from dstack.backend.base import RemoteBackend
from dstack.backend.base import jobs as base_jobs
from dstack.backend.base import repos as base_repos
from dstack.backend.base import runs as base_runs
from dstack.backend.base import secrets as base_secrets
from dstack.backend.base import tags as base_tags
from dstack.backend.gcp.compute import GCPCompute
from dstack.backend.gcp.config import GCPConfig
from dstack.backend.gcp.storage import GCPStorage
from dstack.core.artifact import Artifact
from dstack.core.job import Job, JobHead
from dstack.core.log_event import LogEvent
from dstack.core.repo import RepoAddress, RepoCredentials, RepoData, RepoProtocol
from dstack.core.run import RunHead
from dstack.core.secret import Secret
from dstack.core.tag import TagHead

warnings.filterwarnings("ignore", message=_CLOUD_SDK_CREDENTIALS_WARNING)


class GCPBackend(RemoteBackend):
    def __init__(self):
        self.config = GCPConfig()
        self._storage = GCPStorage(
            project_id=self.config.project_id, bucket_name=self.config.bucket_name
        )
        self._compute = GCPCompute(gcp_config=self.config)
        self.configure()
        self._loaded = True

    @property
    def name(self) -> str:
        return "gcp"

    def configure(self):
        self._storage.configure()

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
        pass

    def list_run_artifact_files(
        self, repo_address: RepoAddress, run_name: str
    ) -> Generator[Artifact, None, None]:
        # TODO: add a flag for non-recursive listing.
        # Backends may implement this via list_run_artifact_files_and_folders()
        pass

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
        pass

    def delete_tag_head(self, repo_address: RepoAddress, tag_head: TagHead):
        base_tags.delete_tag(self._storage, repo_address, tag_head)

    def update_repo_last_run_at(self, repo_address: RepoAddress, last_run_at: int):
        base_repos.update_repo_last_run_at(
            self._storage,
            repo_address,
            last_run_at,
        )

    def get_repo_credentials(self, repo_address: RepoAddress) -> Optional[RepoCredentials]:
        # TODO
        return RepoCredentials(protocol=RepoProtocol.HTTPS, private_key=None, oauth_token=None)

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
