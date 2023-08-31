from typing import Optional

import botocore.exceptions
from boto3 import Session

from dstack._internal.backend.aws import utils as aws_utils
from dstack._internal.backend.aws.compute import AWSCompute
from dstack._internal.backend.aws.config import DEFAULT_REGION, AWSConfig
from dstack._internal.backend.aws.logs import AWSLogging
from dstack._internal.backend.aws.pricing import AWSPricing
from dstack._internal.backend.aws.secrets import AWSSecretsManager
from dstack._internal.backend.aws.storage import AWSStorage
from dstack._internal.backend.base import ComponentBasedBackend
from dstack._internal.core.error import BackendAuthError
from dstack._internal.core.instance import InstancePricing
from dstack._internal.core.job import Job


class AwsBackend(ComponentBasedBackend):
    NAME = "aws"

    def __init__(
        self,
        backend_config: AWSConfig,
    ):
        self.backend_config = backend_config
        if self.backend_config.credentials is not None:
            self._session = Session(
                region_name=self.backend_config.region,
                aws_access_key_id=self.backend_config.credentials.get("access_key"),
                aws_secret_access_key=self.backend_config.credentials.get("secret_key"),
            )
        else:
            self._session = Session(region_name=self.backend_config.region)
        self._storage = AWSStorage(
            s3_client=aws_utils.get_s3_client(self._session),
            bucket_name=self.backend_config.bucket_name,
            namespace=self.name,
        )
        self._compute = AWSCompute(
            session=self._session,
            backend_config=self.backend_config,
        )
        self._secrets_manager = AWSSecretsManager(
            secretsmanager_client=aws_utils.get_secretsmanager_client(
                self._session, region_name=DEFAULT_REGION
            ),
            iam_client=aws_utils.get_iam_client(self._session),
            sts_client=aws_utils.get_sts_client(self._session),
            bucket_name=self.backend_config.bucket_name,
        )
        self._logging = AWSLogging(
            logs_client=aws_utils.get_logs_client(self._session, region_name=DEFAULT_REGION),
            bucket_name=self.backend_config.bucket_name,
        )
        self._pricing = AWSPricing()
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

    def pricing(self) -> AWSPricing:
        return self._pricing

    def run_job(
        self,
        job: Job,
        project_private_key: str,
        offer: InstancePricing,
    ):
        self._logging.create_log_groups_if_not_exist(
            self.backend_config.bucket_name, job.repo_ref.repo_id
        )
        super().run_job(
            job,
            project_private_key=project_private_key,
            offer=offer,
        )

    def _check_credentials(self):
        try:
            self.list_repo_heads()
        except (botocore.exceptions.ClientError, botocore.exceptions.NoCredentialsError):
            raise BackendAuthError()
