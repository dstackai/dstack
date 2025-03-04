from abc import ABC, abstractmethod
from typing import Any, List, Optional

from dstack._internal.core.backends.base import Backend
from dstack._internal.core.errors import BackendInvalidCredentialsError
from dstack._internal.core.models.backends import (
    AnyConfigInfo,
    AnyConfigInfoWithCreds,
)
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.server.models import BackendModel, ProjectModel

# Most clouds allow ~ 40-60 tags/labels per resource.
# We'll introduce our own base limit that can be customized per backend if required.
TAGS_MAX_NUM = 25


class Configurator(ABC):
    TYPE: BackendType

    @abstractmethod
    def validate_config(self, config: AnyConfigInfoWithCreds):
        """
        Validates backend config including backend creds and other parameters.
        Raises `ServerClientError` or its subclass if config is invalid.
        """
        pass

    @abstractmethod
    def create_backend(
        self, project: ProjectModel, config: AnyConfigInfoWithCreds
    ) -> BackendModel:
        """
        Creates BackendModel given backend config and creds.
        It may perform backend initialization, create
        cloud resources such as networks and managed identites, and
        save additional configuration parameters.
        """
        pass

    @abstractmethod
    def get_config_info(self, model: BackendModel, include_creds: bool) -> AnyConfigInfo:
        """
        Constructs backend's ConfigInfo to be returned in API responses.
        Project admins may need to see backend's creds. In this case `include_creds` will be True.
        Otherwise, no sensitive information should be included.
        """
        pass

    @abstractmethod
    def get_backend(self, model: BackendModel) -> Backend:
        """
        Returns Backend instance from config and creds stored in `model`.
        """
        pass


def raise_invalid_credentials_error(
    fields: Optional[List[List[str]]] = None, details: Optional[Any] = None
):
    msg = BackendInvalidCredentialsError.msg
    if details:
        msg += f": {details}"
    raise BackendInvalidCredentialsError(fields=fields, msg=msg)
