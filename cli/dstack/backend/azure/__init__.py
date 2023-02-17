from pathlib import Path
from typing import Generator, List, Optional

from azure.identity import DefaultAzureCredential

from dstack.backend.azure.config import AzureConfig
from dstack.backend.azure.secrets import AzureSecretsManager
from dstack.backend.base import RemoteBackend
from dstack.backend.base import repos as base_repos
from dstack.core.artifact import Artifact
from dstack.core.error import ConfigError
from dstack.core.job import Job, JobHead
from dstack.core.log_event import LogEvent
from dstack.core.repo import RepoAddress, RepoCredentials, RepoData
from dstack.core.run import RunHead
from dstack.core.runners import Runner
from dstack.core.secret import Secret
from dstack.core.tag import TagHead


class AzureBackend(RemoteBackend):
    def __init__(self):
        config = AzureConfig()
        try:
            config.load()
            # XXX: this is flag for availability for using in command `run`.
            self._loaded = True
        except ConfigError:
            self._loaded = False
            return
        self.backend_config = config.config
        self._secrets_manager = AzureSecretsManager(
            credential=DefaultAzureCredential(), vault_url=self.backend_config.secret.url
        )

    @property
    def name(self) -> str:
        return "azure"

    def save_repo_credentials(self, repo_address: RepoAddress, repo_credentials: RepoCredentials):
        base_repos.save_repo_credentials(
            self._secrets_manager,
            repo_address,
            repo_credentials,
        )

    def download_run_artifact_files(
        self,
        repo_address: RepoAddress,
        run_name: str,
        output_dir: Optional[str],
        output_job_dirs: bool = True,
    ):
        raise NotImplementedError

    def upload_job_artifact_files(
        self,
        repo_address: RepoAddress,
        job_id: str,
        artifact_name: str,
        local_path: Path,
    ):
        raise NotImplementedError

    def configure(self):
        raise NotImplementedError

    def create_run(self, repo_address: RepoAddress) -> str:
        raise NotImplementedError

    def create_job(self, job: Job):
        raise NotImplementedError

    def get_job(self, repo_address: RepoAddress, job_id: str) -> Optional[Job]:
        raise NotImplementedError

    def list_jobs(self, repo_address: RepoAddress, run_name: str) -> List[Job]:
        raise NotImplementedError

    def run_job(self, job: Job) -> Runner:
        raise NotImplementedError

    def stop_job(self, repo_address: RepoAddress, job_id: str, abort: bool):
        raise NotImplementedError

    def list_job_heads(
        self, repo_address: RepoAddress, run_name: Optional[str] = None
    ) -> List[JobHead]:
        raise NotImplementedError

    def delete_job_head(self, repo_address: RepoAddress, job_id: str):
        raise NotImplementedError

    def list_run_heads(
        self,
        repo_address: RepoAddress,
        run_name: Optional[str] = None,
        include_request_heads: bool = True,
    ) -> List[RunHead]:
        raise NotImplementedError

    def poll_logs(
        self,
        repo_address: RepoAddress,
        job_heads: List[JobHead],
        start_time: int,
        attached: bool,
    ) -> Generator[LogEvent, None, None]:
        raise NotImplementedError

    def list_run_artifact_files(
        self, repo_address: RepoAddress, run_name: str
    ) -> Generator[Artifact, None, None]:
        # TODO: add a flag for non-recursive listing.
        # Backends may implement this via list_run_artifact_files_and_folders()
        raise NotImplementedError

    def list_tag_heads(self, repo_address: RepoAddress) -> List[TagHead]:
        raise NotImplementedError

    def get_tag_head(self, repo_address: RepoAddress, tag_name: str) -> Optional[TagHead]:
        raise NotImplementedError

    def add_tag_from_run(
        self,
        repo_address: RepoAddress,
        tag_name: str,
        run_name: str,
        run_jobs: Optional[List[Job]],
    ):
        raise NotImplementedError

    def add_tag_from_local_dirs(self, repo_data: RepoData, tag_name: str, local_dirs: List[str]):
        raise NotImplementedError

    def delete_tag_head(self, repo_address: RepoAddress, tag_head: TagHead):
        raise NotImplementedError

    def update_repo_last_run_at(self, repo_address: RepoAddress, last_run_at: int):
        raise NotImplementedError

    def get_repo_credentials(self, repo_address: RepoAddress) -> Optional[RepoCredentials]:
        return base_repos.get_repo_credentials(self._secrets_manager, repo_address)

    def list_secret_names(self, repo_address: RepoAddress) -> List[str]:
        raise NotImplementedError

    def get_secret(self, repo_address: RepoAddress, secret_name: str) -> Optional[Secret]:
        raise NotImplementedError

    def add_secret(self, repo_address: RepoAddress, secret: Secret):
        raise NotImplementedError

    def update_secret(self, repo_address: RepoAddress, secret: Secret):
        raise NotImplementedError

    def delete_secret(self, repo_address: RepoAddress, secret_name: str):
        raise NotImplementedError
