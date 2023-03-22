from pathlib import Path
from typing import Generator, List, Optional

from azure.identity import DefaultAzureCredential

from dstack.backend.azure.compute import AzureCompute
from dstack.backend.azure.config import AzureConfig, AzureConfigurator
from dstack.backend.azure.logs import AzureLogging
from dstack.backend.azure.secrets import AzureSecretsManager
from dstack.backend.azure.storage import AzureStorage
from dstack.backend.base import CloudBackend
from dstack.backend.base import artifacts as base_artifacts
from dstack.backend.base import jobs as base_jobs
from dstack.backend.base import repos as base_repos
from dstack.backend.base import runs as base_runs
from dstack.backend.base import secrets as base_secrets
from dstack.backend.base import tags as base_tags
from dstack.core.artifact import Artifact
from dstack.core.error import ConfigError
from dstack.core.job import Job, JobHead
from dstack.core.log_event import LogEvent
from dstack.core.repo import LocalRepoData, RepoAddress, RepoCredentials
from dstack.core.run import RunHead
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
            account_url=self.config.storage_url,
            container_name=self.config.storage_container,
        )
        self._compute = AzureCompute(
            credential=credential,
            azure_config=self.config,
        )
        self._logging = AzureLogging(
            credential=credential,
            resource_group=self.config.resource_group,
            workspace_id="184b1264-b5e1-489a-8426-654eca432b0c",
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

    def configure(self):
        pass

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
        yield from self._logging.poll_logs(
            storage=self._storage,
            repo_address=repo_address,
            run_name=job_heads[0].run_name,
            start_time=start_time,
        )

    def list_run_artifact_files(self, repo_address: RepoAddress, run_name: str) -> List[Artifact]:
        return base_artifacts.list_run_artifact_files(self._storage, repo_address, run_name)

    def download_run_artifact_files(
        self,
        repo_address: RepoAddress,
        run_name: str,
        output_dir: Optional[str],
        files_path: Optional[str] = None,
    ):
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
        base_artifacts.upload_job_artifact_files(
            storage=self._storage,
            repo_address=repo_address,
            job_id=job_id,
            artifact_name=artifact_name,
            artifact_path=artifact_path,
            local_path=local_path,
        )

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

    def add_tag_from_local_dirs(
        self, repo_data: LocalRepoData, tag_name: str, local_dirs: List[str]
    ):
        base_tags.create_tag_from_local_dirs(
            self._storage,
            repo_data,
            tag_name,
            local_dirs,
            self.type,
        )

    def delete_tag_head(self, repo_address: RepoAddress, tag_head: TagHead):
        base_tags.delete_tag(self._storage, repo_address, tag_head)

    def update_repo_last_run_at(self, repo_address: RepoAddress, last_run_at: int):
        base_repos.update_repo_last_run_at(
            self._storage,
            repo_address,
            last_run_at,
        )

    def get_repo_credentials(self, repo_address: RepoAddress) -> Optional[RepoCredentials]:
        return base_repos.get_repo_credentials(self._secrets_manager, repo_address)

    def list_secret_names(self, repo_address: RepoAddress) -> List[str]:
        return base_secrets.list_secret_names(self._storage, repo_address)

    def get_secret(self, repo_address: RepoAddress, secret_name: str) -> Optional[Secret]:
        return base_secrets.get_secret(self._secrets_manager, repo_address, secret_name)

    def add_secret(self, repo_address: RepoAddress, secret: Secret):
        base_secrets.add_secret(
            self._storage,
            self._secrets_manager,
            repo_address,
            secret,
        )

    def update_secret(self, repo_address: RepoAddress, secret: Secret):
        base_secrets.update_secret(
            self._storage,
            self._secrets_manager,
            repo_address,
            secret,
        )

    def delete_secret(self, repo_address: RepoAddress, secret_name: str):
        base_secrets.delete_secret(
            self._storage,
            self._secrets_manager,
            repo_address,
            secret_name,
        )

    def get_signed_download_url(self, object_key: str) -> str:
        return self._storage.get_signed_download_url(object_key)

    def get_signed_upload_url(self, object_key: str) -> str:
        return self._storage.get_signed_upload_url(object_key)
