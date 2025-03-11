import botocore.exceptions

from dstack._internal.core.backends.aws.compute import AWSCompute
from dstack._internal.core.backends.aws.models import AWSConfig
from dstack._internal.core.backends.base.backend import Backend
from dstack._internal.core.errors import BackendInvalidCredentialsError
from dstack._internal.core.models.backends.base import BackendType


class AWSBackend(Backend):
    TYPE = BackendType.AWS
    COMPUTE_CLASS = AWSCompute

    def __init__(self, config: AWSConfig):
        self.config = config
        self._compute = AWSCompute(self.config)
        self._check_credentials()

    def compute(self) -> AWSCompute:
        return self._compute

    def _check_credentials(self):
        try:
            pass
        except (botocore.exceptions.ClientError, botocore.exceptions.NoCredentialsError):
            raise BackendInvalidCredentialsError()
