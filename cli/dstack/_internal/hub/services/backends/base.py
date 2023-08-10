from abc import ABC, abstractmethod
from typing import Dict, List, Tuple, Union

from dstack._internal.backend.base import Backend
from dstack._internal.hub.db.models import Backend as DBBackend
from dstack._internal.hub.schemas import (
    AnyBackendConfig,
    AnyBackendConfigWithCreds,
    AnyBackendConfigWithCredsPartial,
    BackendValues,
)


class BackendConfigError(Exception):
    def __init__(self, message: str = "", code: str = "invalid_config", fields: List[str] = None):
        self.message = message
        self.code = code
        self.fields = fields if fields is not None else []


class Configurator(ABC):
    NAME = None

    @abstractmethod
    def configure_backend(self, backend_config: AnyBackendConfigWithCredsPartial) -> BackendValues:
        pass

    @abstractmethod
    def create_backend(
        self, project_name: str, backend_config: AnyBackendConfigWithCreds
    ) -> Tuple[Dict, Dict]:
        pass

    @abstractmethod
    def get_backend_config(
        self, db_backend: DBBackend, include_creds: bool
    ) -> Union[AnyBackendConfig, AnyBackendConfigWithCreds]:
        pass

    @abstractmethod
    def get_backend(self, db_backend: DBBackend) -> Backend:
        pass
