import os
import warnings
from typing import Generator, List, Optional

from google.auth._default import _CLOUD_SDK_CREDENTIALS_WARNING
from google.oauth2 import service_account

from dstack.backend.base import CloudBackend
from dstack.backend.base import artifacts as base_artifacts
from dstack.backend.base import cache as base_cache
from dstack.backend.base import jobs as base_jobs
from dstack.backend.base import repos as base_repos
from dstack.backend.base import runs as base_runs
from dstack.backend.base import secrets as base_secrets
from dstack.backend.base import tags as base_tags
from dstack.backend.gcp.compute import GCPCompute
from dstack.backend.gcp.config import GCPConfig, GCPConfigurator
from dstack.backend.gcp.logs import GCPLogging
from dstack.backend.gcp.secrets import GCPSecretsManager
from dstack.backend.gcp.storage import BucketNotFoundError, GCPStorage
from dstack.cli.common import console
from dstack.core.artifact import Artifact
from dstack.core.error import ConfigError
from dstack.core.job import Job, JobHead, JobStatus
from dstack.core.log_event import LogEvent
from dstack.core.repo import Repo, RepoCredentials, RepoHead
from dstack.core.run import RunHead
from dstack.core.secret import Secret
from dstack.core.tag import TagHead
from dstack.utils.common import PathLike

warnings.filterwarnings("ignore", message=_CLOUD_SDK_CREDENTIALS_WARNING)


class GCPBackend(CloudBackend):
    def __init__(self, repo: Optional[Repo], backend_config: Optional[GCPConfig] = None):
        super().__init__(backend_config=backend_config, repo=repo)
        if backend_config is None:
            try:
                backend_config = GCPConfig.load()
            except ConfigError:
                return

        self.config = backend_config

        if self.config.credentials is not None:
            credentials = service_account.Credentials.from_service_account_info(
                self.config.credentials
            )
        elif self.config.credentials_file is not None:
            credentials = service_account.Credentials.from_service_account_file(
                self.config.credentials_file
            )
        else:
            credentials_file = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
            if credentials_file is None:
                return
            credentials = service_account.Credentials.from_service_account_file(credentials_file)

        try:
            self._storage = GCPStorage(
                project_id=self.config.project_id,
                bucket_name=self.config.bucket_name,
                credentials=credentials,
            )
        except BucketNotFoundError:
            return
        self._compute = GCPCompute(gcp_config=self.config, credentials=credentials)
        self._secrets_manager = GCPSecretsManager(
            project_id=self.config.project_id,
            bucket_name=self.config.bucket_name,
            credentials=credentials,
            repo_id=self.repo.repo_id if self.repo else None,
        )
        self._logging = GCPLogging(
            project_id=self.config.project_id,
            bucket_name=self.config.bucket_name,
            credentials=credentials,
        )
        self._loaded = True

    @property
    def name(self) -> str:
        return "gcp"

    def configure(self):
        pass

    def create_run(self) -> str:
        return base_runs.create_run(self._storage, self.type)

    def create_job(self, job: Job):
        if job.artifact_specs and any(art_spec.mount for art_spec in job.artifact_specs):
            console.print("Mount artifacts are not currently supported for 'gcp' backend")
            exit(1)
        base_jobs.create_job(self._storage, job)

    def get_job(self, job_id: str, repo_id: Optional[str] = None) -> Optional[Job]:
        return base_jobs.get_job(self._storage, repo_id or self.repo.repo_id, job_id)

    def list_jobs(self, run_name: str) -> List[Job]:
        return base_jobs.list_jobs(self._storage, self.repo.repo_id, run_name)

    def run_job(self, job: Job, failed_to_start_job_new_status: JobStatus):
        base_jobs.run_job(self._storage, self._compute, job, failed_to_start_job_new_status)

    def stop_job(self, job_id: str, abort: bool):
        base_jobs.stop_job(self._storage, self._compute, self.repo.repo_id, job_id, abort)

    def list_job_heads(
        self, run_name: Optional[str] = None, repo_id: Optional[str] = None
    ) -> List[JobHead]:
        return base_jobs.list_job_heads(self._storage, repo_id or self.repo.repo_id, run_name)

    def delete_job_head(self, job_id: str):
        base_jobs.delete_job_head(self._storage, self.repo.repo_id, job_id)

    def list_run_heads(
        self,
        run_name: Optional[str] = None,
        include_request_heads: bool = True,
        interrupted_job_new_status: JobStatus = JobStatus.FAILED,
        repo_id: Optional[str] = None,
    ) -> List[RunHead]:
        job_heads = self.list_job_heads(run_name, repo_id=repo_id)
        return base_runs.get_run_heads(
            self._storage,
            self._compute,
            job_heads,
            include_request_heads,
            interrupted_job_new_status,
        )

    def poll_logs(
        self,
        job_heads: List[JobHead],
        start_time: int,
        attached: bool,
    ) -> Generator[LogEvent, None, None]:
        yield from self._logging.poll_logs(
            storage=self._storage,
            repo_id=self.repo.repo_id,
            run_name=job_heads[0].run_name,
            start_time=start_time,
        )

    def list_run_artifact_files(self, run_name: str) -> List[Artifact]:
        return base_artifacts.list_run_artifact_files(self._storage, self.repo.repo_id, run_name)

    def download_run_artifact_files(
        self,
        run_name: str,
        output_dir: Optional[PathLike],
        files_path: Optional[PathLike] = None,
    ):
        artifacts = self.list_run_artifact_files(run_name=run_name)
        base_artifacts.download_run_artifact_files(
            storage=self._storage,
            repo_id=self.repo.repo_id,
            artifacts=artifacts,
            output_dir=output_dir,
            files_path=files_path,
        )

    def upload_job_artifact_files(
        self,
        job_id: str,
        artifact_name: str,
        artifact_path: PathLike,
        local_path: PathLike,
    ):
        base_artifacts.upload_job_artifact_files(
            storage=self._storage,
            repo_id=self.repo.repo_id,
            job_id=job_id,
            artifact_name=artifact_name,
            artifact_path=artifact_path,
            local_path=local_path,
        )

    def list_tag_heads(self) -> List[TagHead]:
        return base_tags.list_tag_heads(self._storage, self.repo.repo_id)

    def get_tag_head(self, tag_name: str) -> Optional[TagHead]:
        return base_tags.get_tag_head(self._storage, self.repo.repo_id, tag_name)

    def add_tag_from_run(
        self,
        tag_name: str,
        run_name: str,
        run_jobs: Optional[List[Job]],
    ):
        base_tags.create_tag_from_run(
            self._storage,
            self.repo.repo_id,
            tag_name,
            run_name,
            run_jobs,
        )

    def add_tag_from_local_dirs(self, tag_name: str, local_dirs: List[str]):
        base_tags.create_tag_from_local_dirs(
            self._storage,
            self.repo,
            tag_name,
            local_dirs,
            self.type,
        )

    def delete_tag_head(self, tag_head: TagHead):
        base_tags.delete_tag(self._storage, self.repo.repo_id, tag_head)

    def list_repo_heads(self) -> List[RepoHead]:
        return base_repos.list_repo_heads(self._storage)

    def update_repo_last_run_at(self, last_run_at: int):
        base_repos.update_repo_last_run_at(
            self._storage,
            self.repo.repo_ref,
            last_run_at,
        )

    def get_repo_credentials(self) -> Optional[RepoCredentials]:
        return base_repos.get_repo_credentials(self._secrets_manager)

    def save_repo_credentials(self, repo_credentials: RepoCredentials):
        base_repos.save_repo_credentials(
            self._secrets_manager,
            repo_credentials,
        )

    def list_secret_names(self) -> List[str]:
        return base_secrets.list_secret_names(self._storage, self.repo.repo_id)

    def get_secret(self, secret_name: str) -> Optional[Secret]:
        return base_secrets.get_secret(self._secrets_manager, secret_name)

    def add_secret(self, secret: Secret):
        base_secrets.add_secret(
            self._storage,
            self._secrets_manager,
            secret,
        )

    def update_secret(self, secret: Secret):
        base_secrets.update_secret(
            self._storage,
            self._secrets_manager,
            secret,
        )

    def delete_secret(self, secret_name: str):
        base_secrets.delete_secret(
            self._storage,
            self._secrets_manager,
            secret_name,
        )

    def get_signed_download_url(self, object_key: str) -> str:
        return self._storage.get_signed_download_url(object_key)

    def get_signed_upload_url(self, object_key: str) -> str:
        return self._storage.get_signed_upload_url(object_key)

    @classmethod
    def get_configurator(cls):
        return GCPConfigurator()

    def delete_workflow_cache(self, workflow_name: str):
        base_cache.delete_workflow_cache(
            self._storage, self.repo.repo_id, self.repo.repo_user_id, workflow_name
        )
