from typing import Optional

import boto3

from dstack._internal.backend.aws import utils as aws_utils
from dstack._internal.backend.aws.config import DEFAULT_REGION
from dstack._internal.backend.aws.logs import AWSLogging
from dstack._internal.backend.aws.secrets import AWSSecretsManager
from dstack._internal.backend.aws.storage import AWSStorage
from dstack._internal.backend.base import ComponentBasedBackend
from dstack._internal.backend.lambdalabs.compute import LambdaCompute
from dstack._internal.backend.lambdalabs.config import LambdaConfig
from dstack._internal.backend.lambdalabs.pricing import LambdaPricing
from dstack._internal.core.instance import InstancePricing
from dstack._internal.core.job import Job


class LambdaBackend(ComponentBasedBackend):
    NAME = "lambda"

    def __init__(
        self,
        backend_config: LambdaConfig,
    ):
        self.backend_config = backend_config
        self._compute = LambdaCompute(lambda_config=self.backend_config)
        self._session = boto3.session.Session(
            region_name=self.backend_config.storage_config.region,
            aws_access_key_id=self.backend_config.storage_config.credentials.access_key,
            aws_secret_access_key=self.backend_config.storage_config.credentials.secret_key,
        )
        self._storage = AWSStorage(
            s3_client=aws_utils.get_s3_client(self._session),
            bucket_name=self.backend_config.storage_config.bucket,
            namespace=self.name,
        )
        self._secrets_manager = AWSSecretsManager(
            secretsmanager_client=aws_utils.get_secretsmanager_client(
                self._session, region_name=DEFAULT_REGION
            ),
            iam_client=aws_utils.get_iam_client(self._session),
            sts_client=aws_utils.get_sts_client(self._session),
            bucket_name=self.backend_config.storage_config.bucket,
        )
        self._logging = AWSLogging(
            logs_client=aws_utils.get_logs_client(self._session, region_name=DEFAULT_REGION),
            bucket_name=self.backend_config.storage_config.bucket,
        )
        self._pricing = LambdaPricing()

    @classmethod
    def load(cls) -> Optional["LambdaBackend"]:
        config = LambdaConfig.load()
        if config is None:
            return None
        return cls(config)

    def storage(self) -> AWSStorage:
        return self._storage

    def compute(self) -> LambdaCompute:
        return self._compute

    def secrets_manager(self) -> AWSSecretsManager:
        return self._secrets_manager

    def logging(self) -> AWSLogging:
        return self._logging

    def pricing(self) -> LambdaPricing:
        return self._pricing

    def run_job(
        self,
        job: Job,
        project_private_key: str,
        offer: InstancePricing,
    ):
        self._logging.create_log_groups_if_not_exist(
            self.backend_config.storage_config.bucket, job.repo_ref.repo_id
        )
        super().run_job(
            job,
            project_private_key=project_private_key,
            offer=offer,
        )
