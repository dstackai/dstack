from dstack._internal.core.backends.base import Backend
from dstack._internal.core.backends.oci.compute import OCICompute
from dstack._internal.core.backends.oci.config import OCIConfig
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.settings import FeatureFlags


class OCIBackend(Backend):
    if FeatureFlags.OCI_BACKEND:
        TYPE: BackendType = BackendType.OCI

    def __init__(self, config: OCIConfig):
        self.config = config
        self._compute = OCICompute(self.config)

    def compute(self) -> OCICompute:
        return self._compute
