from datetime import datetime
from typing import Generator, Optional

import boto3
from botocore.client import BaseClient

from dstack._internal.backend.aws import logs
from dstack._internal.backend.aws.compute import AWSCompute
from dstack._internal.backend.aws.config import AWSConfig
from dstack._internal.backend.aws.secrets import AWSSecretsManager
from dstack._internal.backend.aws.storage import AWSStorage
from dstack._internal.backend.base import ComponentBasedBackend
from dstack._internal.backend.base import runs as base_runs
from dstack._internal.core.log_event import LogEvent


class AwsBackend(ComponentBasedBackend):
    NAME = "aws"

    def __init__(
        self,
        backend_config: AWSConfig,
    ):
        self.backend_config = backend_config
        if self.backend_config.credentials is not None:
            self._session = boto3.session.Session(
                region_name=self.backend_config.region_name,
                aws_access_key_id=self.backend_config.credentials.get("access_key"),
                aws_secret_access_key=self.backend_config.credentials.get("secret_key"),
            )
        else:
            self._session = boto3.session.Session(region_name=self.backend_config.region_name)
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

    @classmethod
    def load(cls) -> Optional["AwsBackend"]:
        config = AWSConfig.load()
        if config is None:
            return None
        return cls(
            backend_config=config,
        )

    def storage(self) -> AWSStorage:
        return self._storage

    def compute(self) -> AWSCompute:
        return self._compute

    def secrets_manager(self) -> AWSSecretsManager:
        return self._secrets_manager

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
        return self._session.client(client_name)

    def create_run(self, repo_id: str) -> str:
        logs.create_log_groups_if_not_exist(
            self._logs_client(), self.backend_config.bucket_name, repo_id
        )
        return base_runs.create_run(self._storage)

    def poll_logs(
        self,
        repo_id: str,
        run_name: str,
        start_time: datetime,
        end_time: Optional[datetime] = None,
        descending: bool = False,
        diagnose: bool = False,
    ) -> Generator[LogEvent, None, None]:
        return logs.poll_logs(
            self._storage,
            self._logs_client(),
            self.backend_config.bucket_name,
            repo_id,
            run_name,
            start_time,
            end_time,
            descending,
            diagnose,
        )
