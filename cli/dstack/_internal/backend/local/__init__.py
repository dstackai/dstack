from typing import Optional

from dstack._internal.backend.base import ComponentBasedBackend
from dstack._internal.backend.base import build as base_build
from dstack._internal.backend.local.compute import LocalCompute
from dstack._internal.backend.local.config import LocalConfig
from dstack._internal.backend.local.logs import LocalLogging
from dstack._internal.backend.local.secrets import LocalSecretsManager
from dstack._internal.backend.local.storage import LocalStorage
from dstack._internal.core.build import BuildPlan
from dstack._internal.core.job import Job


class LocalBackend(ComponentBasedBackend):
    NAME = "local"

    def __init__(
        self,
        backend_config: LocalConfig,
    ):
        self.backend_config = backend_config
        self._storage = LocalStorage(self.backend_config.backend_dir)
        self._compute = LocalCompute(self.backend_config)
        self._secrets_manager = LocalSecretsManager(self.backend_config.backend_dir)
        self._logging = LocalLogging(self.backend_config)

    @classmethod
    def load(cls) -> Optional["LocalBackend"]:
        config = LocalConfig.load()
        if config is None:
            return None
        return cls(backend_config=config)

    def storage(self) -> LocalStorage:
        return self._storage

    def compute(self) -> LocalCompute:
        return self._compute

    def secrets_manager(self) -> LocalSecretsManager:
        return self._secrets_manager

    def logging(self) -> LocalLogging:
        return self._logging

    def predict_build_plan(self, job: Job) -> BuildPlan:
        # guess platform from uname
        return base_build.predict_build_plan(self.storage(), job, platform=None)
