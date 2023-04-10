from pathlib import Path
from typing import Generator, List, Optional

import boto3
from botocore.client import BaseClient

from dstack.backend.aws import config, logs
from dstack.backend.aws.compute import AWSCompute
from dstack.backend.aws.config import AWSConfig, AWSConfigurator
from dstack.backend.aws.secrets import AWSSecretsManager
from dstack.backend.aws.storage import AWSStorage
from dstack.backend.base import CloudBackend
from dstack.backend.base import artifacts as base_artifacts
from dstack.backend.base import cache as base_cache
from dstack.backend.base import jobs as base_jobs
from dstack.backend.base import repos as base_repos
from dstack.backend.base import runs as base_runs
from dstack.backend.base import secrets as base_secrets
from dstack.backend.base import tags as base_tags
from dstack.core.artifact import Artifact
from dstack.core.error import ConfigError
from dstack.core.job import Job, JobHead, JobStatus
from dstack.core.log_event import LogEvent
from dstack.core.repo import LocalRepoData, RepoAddress, RepoCredentials, RepoHead
from dstack.core.run import RunHead
from dstack.core.secret import Secret
from dstack.core.tag import TagHead


class AwsBackend(CloudBackend):
    _session: Optional[boto3.Session] = None
    backend_config: AWSConfig

    @property
    def name(self):
        return "aws"

    def __init__(self, backend_config: Optional[AWSConfig] = None):
        if backend_config is None:
            self.backend_config = AWSConfig()
            try:
                self.backend_config.load()
                self._loaded = True
            except ConfigError:
                self._loaded = False
                return
        else:
            self.backend_config = backend_config
            self._loaded = True

        if self.backend_config.credentials is not None:
            self._session = boto3.session.Session(
                region_name=self.backend_config.region_name,
                aws_access_key_id=self.backend_config.credentials.get("access_key"),
                aws_secret_access_key=self.backend_config.credentials.get("secret_key"),
            )

        self._storage = AWSStorage(
            s3_client=self._s3_client(), bucket_name=self.backend_config.bucket_name
        )
        self._compute = AWSCompute(
            ec2_client=self._ec2_client(),
            iam_client=self._iam_client(),
            bucket_name=self.backend_config.bucket_name,
            region_name=self.backend_config.region_name,
            subnet_id=self.backend_config.subnet_id,
        )
        self._secrets_manager = AWSSecretsManager(
            secretsmanager_client=self._secretsmanager_client(),
            iam_client=self._iam_client(),
            sts_client=self._sts_client(),
            bucket_name=self.backend_config.bucket_name,
        )

    def _s3_client(self) -> BaseClient:
        return self._get_client("s3")

    def _ec2_client(self) -> BaseClient:
        return self._get_client("ec2")

    def _iam_client(self) -> BaseClient:
        return self._get_client("iam")

    def _logs_client(self) -> BaseClient:
        return self._get_client("logs")

    def _secretsmanager_client(self) -> BaseClient:
        return self._get_client("secretsmanager")

    def _sts_client(self) -> BaseClient:
        return self._get_client("sts")

    def _get_client(self, client_name: str) -> BaseClient:
        if self._session is None:
            self._session = boto3.Session(
                profile_name=self.backend_config.profile_name,
                region_name=self.backend_config.region_name,
            )
        return self._session.client(client_name)

    def configure(self):
        config.configure(
            self._ec2_client(),
            self._iam_client(),
            self.backend_config.bucket_name,
            self.backend_config.subnet_id,
        )

    def create_run(self, repo_address: RepoAddress) -> str:
        logs.create_log_group_if_not_exists(
            self._logs_client(), self.backend_config.bucket_name, repo_address
        )
        return base_runs.create_run(self._storage, repo_address, self.type)

    def create_job(self, job: Job):
        base_jobs.create_job(self._storage, job)

    def get_job(self, repo_address: RepoAddress, job_id: str) -> Optional[Job]:
        return base_jobs.get_job(self._storage, repo_address, job_id)

    def list_jobs(self, repo_address: RepoAddress, run_name: str) -> List[Job]:
        return base_jobs.list_jobs(self._storage, repo_address, run_name)

    def run_job(self, job: Job, failed_to_start_job_new_status: JobStatus):
        base_jobs.run_job(self._storage, self._compute, job, failed_to_start_job_new_status)

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
        interrupted_job_new_status: JobStatus = JobStatus.FAILED,
    ) -> List[RunHead]:
        job_heads = self.list_job_heads(repo_address, run_name)
        return base_runs.get_run_heads(
            self._storage,
            self._compute,
            job_heads,
            include_request_heads,
            interrupted_job_new_status,
        )

    def poll_logs(
        self,
        repo_address: RepoAddress,
        job_heads: List[JobHead],
        start_time: int,
        attached: bool,
    ) -> Generator[LogEvent, None, None]:
        return logs.poll_logs(
            self._storage,
            self._compute,
            self._logs_client(),
            self.backend_config.bucket_name,
            repo_address,
            job_heads,
            start_time,
            attached,
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

    def list_repo_heads(self) -> List[RepoHead]:
        return base_repos.list_repo_heads(self._storage)

    def update_repo_last_run_at(self, repo_address: RepoAddress, last_run_at: int):
        base_repos.update_repo_last_run_at(
            self._storage,
            repo_address,
            last_run_at,
        )

    def get_repo_credentials(self, repo_address: RepoAddress) -> Optional[RepoCredentials]:
        return base_repos.get_repo_credentials(self._secrets_manager, repo_address)

    def save_repo_credentials(self, repo_address: RepoAddress, repo_credentials: RepoCredentials):
        base_repos.save_repo_credentials(
            self._secrets_manager,
            repo_address,
            repo_credentials,
        )

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

    def get_configurator(self):
        return AWSConfigurator()

    def delete_workflow_cache(self, repo_address: RepoAddress, username: str, workflow_name: str):
        base_cache.delete_workflow_cache(self._storage, repo_address, username, workflow_name)
