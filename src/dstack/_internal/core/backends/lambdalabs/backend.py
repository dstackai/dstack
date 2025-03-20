from dstack._internal.core.backends.base.backend import Backend
from dstack._internal.core.backends.lambdalabs.compute import LambdaCompute
from dstack._internal.core.backends.lambdalabs.models import LambdaConfig
from dstack._internal.core.models.backends.base import BackendType


class LambdaBackend(Backend):
    TYPE = BackendType.LAMBDA
    COMPUTE_CLASS = LambdaCompute

    def __init__(self, config: LambdaConfig):
        self.config = config
        self._compute = LambdaCompute(self.config)
        # self._check_credentials()

    def compute(self) -> LambdaCompute:
        return self._compute
