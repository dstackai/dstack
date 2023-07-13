from typing import Optional

import botocore.exceptions
from boto3 import Session

from dstack._internal.backend.aws import utils as aws_utils
from dstack._internal.backend.aws.compute import AWSCompute
from dstack._internal.backend.aws.config import AWSConfig
from dstack._internal.backend.aws.logs import AWSLogging
from dstack._internal.backend.aws.secrets import AWSSecretsManager
from dstack._internal.backend.aws.storage import AWSStorage
from dstack._internal.backend.base import ComponentBasedBackend
from dstack._internal.backend.base import runs as base_runs
from dstack._internal.core.error import BackendAuthError


class AwsBackend(ComponentBasedBackend):
    NAME = "aws"

    def __init__(
        self,
        backend_config: AWSConfig,
    ):
        self.backend_config = backend_config
        if self.backend_config.credentials is not None:
            self._session = Session(
                region_name=self.backend_config.region_name,
                aws_access_key_id=self.backend_config.credentials.get("access_key"),
                aws_secret_access_key=self.backend_config.credentials.get("secret_key"),
            )
        else:
            self._session = Session(region_name=self.backend_config.region_name)
        self._storage = AWSStorage(
            s3_client=aws_utils.get_s3_client(self._session),
            bucket_name=self.backend_config.bucket_name,
        )
        self._compute = AWSCompute(
            session=self._session,
            backend_config=self.backend_config,
        )
        self._secrets_manager = AWSSecretsManager(
            secretsmanager_client=aws_utils.get_secretsmanager_client(self._session),
            iam_client=aws_utils.get_iam_client(self._session),
            sts_client=aws_utils.get_sts_client(self._session),
            bucket_name=self.backend_config.bucket_name,
        )
        self._logging = AWSLogging(
            logs_client=aws_utils.get_logs_client(self._session),
            bucket_name=self.backend_config.bucket_name,
        )
        self._check_credentials()

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
            aws_utils.get_logs_client(self._session), self.backend_config.bucket_name, repo_id
        )
        return base_runs.create_run(self._storage)

    def _check_credentials(self):
        try:
            self.list_repo_heads()
        except (botocore.exceptions.ClientError, botocore.exceptions.NoCredentialsError):
            raise BackendAuthError()
