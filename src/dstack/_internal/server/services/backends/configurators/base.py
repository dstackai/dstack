from abc import ABC, abstractmethod
from typing import List, Optional

from dstack._internal.core.backends.base import Backend
from dstack._internal.core.errors import BackendInvalidCredentialsError
from dstack._internal.core.models.backends import (
    AnyConfigInfo,
    AnyConfigInfoWithCreds,
    AnyConfigInfoWithCredsPartial,
    AnyConfigValues,
)
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.server.models import BackendModel, ProjectModel


class Configurator(ABC):
    TYPE: BackendType

    @abstractmethod
    def get_default_configs(self) -> List[AnyConfigInfoWithCreds]:
        pass

    @abstractmethod
    def get_config_values(self, config: AnyConfigInfoWithCredsPartial) -> AnyConfigValues:
        pass

    @abstractmethod
    def create_backend(
        self, project: ProjectModel, config: AnyConfigInfoWithCreds
    ) -> BackendModel:
        pass

    @abstractmethod
    def get_config_info(self, model: BackendModel, include_creds: bool) -> AnyConfigInfo:
        pass

    @abstractmethod
    def get_backend(self, model: BackendModel) -> Backend:
        pass


def raise_invalid_credentials_error(fields: Optional[List[List[str]]] = None):
    raise BackendInvalidCredentialsError(fields=fields)
