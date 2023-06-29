from datetime import datetime
from typing import Generator, List, Optional

from dstack._internal.backend.base import ComponentBasedBackend
from dstack._internal.backend.local import logs
from dstack._internal.backend.local.compute import LocalCompute
from dstack._internal.backend.local.config import LocalConfig
from dstack._internal.backend.local.secrets import LocalSecretsManager
from dstack._internal.backend.local.storage import LocalStorage
from dstack._internal.core.log_event import LogEvent


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
            self.backend_config,
            self._storage,
            repo_id,
            run_name,
            start_time,
            end_time,
            descending,
            diagnose,
        )
