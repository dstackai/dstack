import boto3.session
import botocore.exceptions

from dstack._internal.core.backends.aws.compute import AWSCompute
from dstack._internal.core.backends.aws.config import AWSConfig
from dstack._internal.core.backends.aws.pricing import AWSPricing
from dstack._internal.core.backends.base import Backend
from dstack._internal.core.errors import BackendInvalidCredentialsError


class AwsBackend(Backend):
    NAME = "aws"

    def __init__(self, config: AWSConfig):
        self.config = config
        if self.config.creds.type == "access_key":
            self._session = boto3.session.Session(
                region_name=self.config.region,
                aws_access_key_id=self.config.creds.access_key,
                aws_secret_access_key=self.config.creds.secret_key,
            )
        self._compute = AWSCompute(
            session=self._session,
            backend_config=self.config,
        )
        self._pricing = AWSPricing()
        self._check_credentials()

    def compute(self) -> AWSCompute:
        return self._compute

    def pricing(self) -> AWSPricing:
        return self._pricing

    def _check_credentials(self):
        try:
            # TODO
            self.list_repo_heads()
        except (botocore.exceptions.ClientError, botocore.exceptions.NoCredentialsError):
            raise BackendInvalidCredentialsError()
