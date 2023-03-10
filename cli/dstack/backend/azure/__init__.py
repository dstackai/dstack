from pathlib import Path
from typing import Generator, List, Optional

from azure.identity import DefaultAzureCredential
from azure.mgmt.subscription import SubscriptionClient

from dstack.backend.azure.compute import AzureCompute
from dstack.backend.azure.config import AzureConfig, AzureConfigurator
from dstack.backend.azure.secrets import AzureSecretsManager
from dstack.backend.azure.storage import AzureStorage
from dstack.backend.base import CloudBackend
from dstack.backend.base import jobs as base_jobs
from dstack.backend.base import repos as base_repos
from dstack.backend.base import runs as base_runs
from dstack.core.artifact import Artifact
from dstack.core.error import ConfigError
from dstack.core.job import Job, JobHead
from dstack.core.log_event import LogEvent
from dstack.core.repo import RepoAddress, RepoCredentials, RepoData
from dstack.core.run import RunHead
from dstack.core.runners import Runner
from dstack.core.secret import Secret
from dstack.core.tag import TagHead


class AzureBackend(CloudBackend):
    def __init__(self, backend_config: Optional[AzureConfig] = None):
        if backend_config is None:
            try:
                backend_config = AzureConfig.load()
            except ConfigError:
                return

        self.config = backend_config

        credential = DefaultAzureCredential()
        self._secrets_manager = AzureSecretsManager(
            credential=credential,
            vault_url=self.config.secret_url,
        )
        # https://learn.microsoft.com/en-us/azure/storage/blobs/assign-azure-role-data-access?tabs=portal
        self._storage = AzureStorage(
            credential=credential,
            subscription_id=self.config.subscription_id,
            account_url=self.config.storage_url,
            container_name=self.config.storage_container,
        )
        self._compute = AzureCompute(
            credential=credential,
            subscription_id=self.config.subscription_id,
            tenant_id=self.config.tenant_id,
            location=self.config.location,
            secret_vault_name=self.config.secret_url.host.split(".", 1)[0],
            secret_vault_resource_group=self.config.secret_resource_group,
            storage_account_name=self._storage.get_account_name(),
            backend_config=self.config,
        )
        self._loaded = True

    @property
    def name(self) -> str:
        return "azure"

    def get_configurator(self):
        return AzureConfigurator()

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
        artifact_path: str,
        local_path: Path,
    ):
        raise NotImplementedError

    def configure(self):
        raise NotImplementedError

    def create_run(self, repo_address: RepoAddress) -> str:
        return base_runs.create_run(self._storage, repo_address, self.type)

    def create_job(self, job: Job):
        base_jobs.create_job(self._storage, job)

    def get_job(self, repo_address: RepoAddress, job_id: str) -> Optional[Job]:
        raise NotImplementedError

    def list_jobs(self, repo_address: RepoAddress, run_name: str) -> List[Job]:
        raise NotImplementedError

    def run_job(self, job: Job):
        base_jobs.run_job(self._storage, self._compute, job)

    def stop_job(self, repo_address: RepoAddress, job_id: str, abort: bool):
        base_jobs.stop_job(self._storage, self._compute, repo_address, job_id, abort)

    def list_job_heads(
        self, repo_address: RepoAddress, run_name: Optional[str] = None
    ) -> List[JobHead]:
        return base_jobs.list_job_heads(self._storage, repo_address, run_name)

    def delete_job_head(self, repo_address: RepoAddress, job_id: str):
        raise NotImplementedError

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
        base_repos.update_repo_last_run_at(
            self._storage,
            repo_address,
            last_run_at,
        )

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

    def get_signed_download_url(self, object_key: str) -> str:
        raise NotImplementedError

    def get_signed_upload_url(self, object_key: str) -> str:
        raise NotImplementedError
