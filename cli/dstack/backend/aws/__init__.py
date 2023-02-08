from pathlib import Path
from typing import Dict, Generator, List, Optional, Tuple

import boto3
from botocore.client import BaseClient

from dstack.backend.aws import (
    artifacts,
    config,
    jobs,
    logs,
    repos,
    run_names,
    runners,
    runs,
    secrets,
    tags,
)
from dstack.backend.aws.config import AWSConfig
from dstack.backend.aws.storage import AWSStorage
from dstack.backend.base import RemoteBackend
from dstack.backend.base import jobs as base_jobs
from dstack.core.artifact import Artifact
from dstack.core.error import ConfigError
from dstack.core.job import Job, JobHead
from dstack.core.log_event import LogEvent
from dstack.core.repo import LocalRepoData, RepoAddress, RepoCredentials, RepoHead
from dstack.core.run import RunHead
from dstack.core.secret import Secret
from dstack.core.tag import TagHead


class AwsBackend(RemoteBackend):
    @property
    def name(self):
        return "aws"

    def __init__(self):
        self.backend_config = AWSConfig()
        try:
            self.backend_config.load()
            self._loaded = True
        except ConfigError:
            self._loaded = False
        self._storage = AWSStorage(
            s3_client=self._s3_client(), bucket_name=self.backend_config.bucket_name
        )

    def _s3_client(self) -> BaseClient:
        session = boto3.Session(
            profile_name=self.backend_config.profile_name,
            region_name=self.backend_config.region_name,
        )
        return session.client("s3")

    def _ec2_client(self) -> BaseClient:
        session = boto3.Session(
            profile_name=self.backend_config.profile_name,
            region_name=self.backend_config.region_name,
        )
        return session.client("ec2")

    def _iam_client(self) -> BaseClient:
        session = boto3.Session(
            profile_name=self.backend_config.profile_name,
            region_name=self.backend_config.region_name,
        )
        return session.client("iam")

    def _logs_client(self) -> BaseClient:
        session = boto3.Session(
            profile_name=self.backend_config.profile_name,
            region_name=self.backend_config.region_name,
        )
        return session.client("logs")

    def _secretsmanager_client(self) -> BaseClient:
        session = boto3.Session(
            profile_name=self.backend_config.profile_name,
            region_name=self.backend_config.region_name,
        )
        return session.client("secretsmanager")

    def _sts_client(self) -> BaseClient:
        session = boto3.Session(
            profile_name=self.backend_config.profile_name,
            region_name=self.backend_config.region_name,
        )
        return session.client("sts")

    def configure(self):
        config.configure(
            self._ec2_client(),
            self._iam_client(),
            self.backend_config.bucket_name,
            self.backend_config.subnet_id,
        )

    def create_run(self, repo_address: RepoAddress) -> str:
        return runs.create_run(
            self._s3_client(),
            self._logs_client(),
            self.backend_config.bucket_name,
            repo_address,
        )

    def create_job(self, job: Job):
        base_jobs.create_job(self._storage, job)

    def get_job(self, repo_address: RepoAddress, job_id: str) -> Optional[Job]:
        return base_jobs.get_job(self._storage, repo_address, job_id)

    def list_jobs(self, repo_address: RepoAddress, run_name: str) -> List[Job]:
        return base_jobs.list_jobs(self._storage, repo_address, run_name)

    def run_job(self, job: Job):
        runners.run_job(
            self._logs_client(),
            self._ec2_client(),
            self._iam_client(),
            self._s3_client(),
            self.backend_config.bucket_name,
            self.backend_config.region_name,
            self.backend_config.subnet_id,
            job,
        )

    def stop_job(self, repo_address: RepoAddress, job_id: str, abort: bool):
        runners.stop_job(
            self._ec2_client(),
            self._s3_client(),
            self.backend_config.bucket_name,
            repo_address,
            job_id,
            abort,
        )

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
        return runs.get_run_heads(
            self._ec2_client(),
            self._s3_client(),
            self.backend_config.bucket_name,
            job_heads,
            include_request_heads,
        )

    def poll_logs(
        self,
        repo_address: RepoAddress,
        job_heads: List[JobHead],
        start_time: int,
        attached: bool,
    ) -> Generator[LogEvent, None, None]:
        return logs.poll_logs(
            self._ec2_client(),
            self._s3_client(),
            self._logs_client(),
            self.backend_config.bucket_name,
            repo_address,
            job_heads,
            start_time,
            attached,
        )

    def list_run_artifact_files(
        self, repo_address: RepoAddress, run_name: str
    ) -> Generator[Artifact, None, None]:
        return artifacts.list_run_artifact_files(
            self._s3_client(), self.backend_config.bucket_name, repo_address, run_name
        )

    def download_run_artifact_files(
        self,
        repo_address: RepoAddress,
        run_name: str,
        output_dir: Optional[str],
        output_job_dirs: bool = True,
    ):
        artifacts.download_run_artifact_files(
            self._s3_client(),
            self.backend_config.bucket_name,
            repo_address,
            run_name,
            output_dir,
            output_job_dirs,
        )

    def upload_job_artifact_files(
        self,
        repo_address: RepoAddress,
        job_id: str,
        artifact_name: str,
        local_path: Path,
    ):
        artifacts.upload_job_artifact_files(
            s3_client=self._s3_client(),
            bucket_name=self.backend_config.bucket_name,
            repo_address=repo_address,
            job_id=job_id,
            artifact_name=artifact_name,
            local_path=local_path,
        )

    def list_tag_heads(self, repo_address: RepoAddress) -> List[TagHead]:
        return tags.list_tag_heads(
            self._s3_client(), self.backend_config.bucket_name, repo_address
        )

    def get_tag_head(self, repo_address: RepoAddress, tag_name: str) -> Optional[TagHead]:
        return tags.get_tag_head(
            self._s3_client(), self.backend_config.bucket_name, repo_address, tag_name
        )

    def add_tag_from_run(
        self,
        repo_address: RepoAddress,
        tag_name: str,
        run_name: str,
        run_jobs: Optional[List[Job]],
    ):
        tags.create_tag_from_run(
            self._s3_client(),
            self.backend_config.bucket_name,
            repo_address,
            tag_name,
            run_name,
            run_jobs,
        )

    def add_tag_from_local_dirs(
        self, repo_data: LocalRepoData, tag_name: str, local_dirs: List[str]
    ):
        tags.create_tag_from_local_dirs(
            self._s3_client(),
            self._logs_client(),
            self.backend_config.bucket_name,
            repo_data,
            tag_name,
            local_dirs,
        )

    def delete_tag_head(self, repo_address: RepoAddress, tag_head: TagHead):
        tags.delete_tag(self._s3_client(), self.backend_config.bucket_name, repo_address, tag_head)

    def update_repo_last_run_at(self, repo_address: RepoAddress, last_run_at: int):
        repos.update_repo_last_run_at(
            self._s3_client(),
            self.backend_config.bucket_name,
            repo_address,
            last_run_at,
        )

    def get_repo_credentials(self, repo_address: RepoAddress) -> Optional[RepoCredentials]:
        return repos.get_repo_credentials(
            self._secretsmanager_client(), self.backend_config.bucket_name, repo_address
        )

    def save_repo_credentials(self, repo_address: RepoAddress, repo_credentials: RepoCredentials):
        repos.save_repo_credentials(
            self._sts_client(),
            self._iam_client(),
            self._secretsmanager_client(),
            self.backend_config.bucket_name,
            repo_address,
            repo_credentials,
        )

    def list_secret_names(self, repo_address: RepoAddress) -> List[str]:
        return secrets.list_secret_names(
            self._s3_client(), self.backend_config.bucket_name, repo_address
        )

    def get_secret(self, repo_address: RepoAddress, secret_name: str) -> Optional[Secret]:
        return secrets.get_secret(
            self._secretsmanager_client(),
            self.backend_config.bucket_name,
            repo_address,
            secret_name,
        )

    def add_secret(self, repo_address: RepoAddress, secret: Secret):
        return secrets.add_secret(
            self._sts_client(),
            self._iam_client(),
            self._secretsmanager_client(),
            self._s3_client(),
            self.backend_config.bucket_name,
            repo_address,
            secret,
        )

    def update_secret(self, repo_address: RepoAddress, secret: Secret):
        return secrets.update_secret(
            self._secretsmanager_client(),
            self._s3_client(),
            self.backend_config.bucket_name,
            repo_address,
            secret,
        )

    def delete_secret(self, repo_address: RepoAddress, secret_name: str):
        return secrets.delete_secret(
            self._secretsmanager_client(),
            self._s3_client(),
            self.backend_config.bucket_name,
            repo_address,
            secret_name,
        )
