from abc import ABC, abstractmethod
from typing import Dict, List, Tuple, Union

from dstack._internal.backend.base import Backend
from dstack._internal.hub.db.models import Project
from dstack._internal.hub.models import (
    AnyProjectConfig,
    AnyProjectConfigWithCreds,
    AnyProjectConfigWithCredsPartial,
    ProjectValues,
)


class BackendConfigError(Exception):
    def __init__(self, message: str = "", code: str = "invalid_config", fields: List[str] = None):
        self.message = message
        self.code = code
        self.fields = fields if fields is not None else []


class Configurator(ABC):
    NAME = None

    @abstractmethod
    def configure_project(self, project_config: AnyProjectConfigWithCredsPartial) -> ProjectValues:
        pass

    @abstractmethod
    def create_project(self, project_config: AnyProjectConfigWithCreds) -> Tuple[Dict, Dict]:
        pass

    @abstractmethod
    def get_project_config(
        self, project: Project, include_creds: bool
    ) -> Union[AnyProjectConfig, AnyProjectConfigWithCreds]:
        pass

    @abstractmethod
    def get_backend(self, project: Project) -> Backend:
        pass
