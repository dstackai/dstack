from abc import ABC, abstractmethod

from dstack._internal.core.backends.base import Backend
from dstack._internal.core.models.backends import (
    AnyBackendConfig,
    AnyBackendConfigWithCreds,
    BackendType,
    ConfigValues,
)
from dstack._internal.server.models import BackendModel


class Configurator(ABC):
    NAME: BackendType

    @abstractmethod
    def get_config_values(self, backend_config: AnyBackendConfigWithCreds) -> ConfigValues:
        pass

    @abstractmethod
    def create_backend(self, backend_config: AnyBackendConfigWithCreds) -> BackendModel:
        pass

    @abstractmethod
    def get_backend_config(
        self, backend_model: BackendModel, include_creds: bool
    ) -> AnyBackendConfig:
        pass

    @abstractmethod
    def get_backend(self, backend_model: BackendModel) -> Backend:
        pass
