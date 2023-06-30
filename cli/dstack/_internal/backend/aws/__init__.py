from typing import Optional

import boto3
from botocore.client import BaseClient

from dstack._internal.backend.aws.compute import AWSCompute
from dstack._internal.backend.aws.config import AWSConfig
from dstack._internal.backend.aws.logs import AWSLogging
from dstack._internal.backend.aws.secrets import AWSSecretsManager
from dstack._internal.backend.aws.storage import AWSStorage
from dstack._internal.backend.base import ComponentBasedBackend
from dstack._internal.backend.base import runs as base_runs


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
        self._logging = AWSLogging(
            logs_client=self._logs_client(),
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

    def logging(self) -> AWSLogging:
        return self._logging

    def create_run(self, repo_id: str) -> str:
        self._logging.create_log_groups_if_not_exist(
            self._logs_client(), self.backend_config.bucket_name, repo_id
        )
        return base_runs.create_run(self._storage)

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
