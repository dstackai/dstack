from abc import ABC, abstractmethod
from typing import Any, ClassVar, List, Optional
from uuid import UUID

from dstack._internal.core.backends.base.backend import Backend
from dstack._internal.core.backends.models import (
    AnyBackendConfig,
    AnyBackendConfigWithCreds,
)
from dstack._internal.core.errors import BackendInvalidCredentialsError
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.common import CoreModel

# Most clouds allow ~ 40-60 tags/labels per resource.
# We'll introduce our own base limit that can be customized per backend if required.
TAGS_MAX_NUM = 25


class BackendRecord(CoreModel):
    """
    This model includes backend parameters to store in the DB.
    """

    # `config` stores text-encoded non-sensitive backend config parameters (e.g. json)
    config: str
    # `auth` stores text-encoded sensitive backend config parameters (e.g. json).
    # Configurator should not encrypt/decrypt it. This is done by the caller.
    auth: str


class StoredBackendRecord(BackendRecord):
    """
    This model includes backend parameters stored in the DB.
    """

    # IDs of DB models.
    # Can be used by externally-registered Configurator to work with the DB directly.
    project_id: UUID
    backend_id: UUID


class Configurator(ABC):
    """
    `Configurator` is responsible for configuring backends
    and initializing `Backend` instances from backend configs.
    Every backend must implement `Configurator` and register it
    in `dstack._internal.core.backends.configurators`.
    """

    TYPE: ClassVar[BackendType]
    # `BACKEND_CLASS` is used to introspect backend features without initializing it.
    BACKEND_CLASS: ClassVar[type[Backend]]

    @abstractmethod
    def validate_config(self, config: AnyBackendConfigWithCreds, default_creds_enabled: bool):
        """
        Validates backend config including backend creds and other parameters.
        Raises `ServerClientError` or its subclass if config is invalid.
        If the backend supports default creds and not `default_creds_enabled`, should raise an error.
        """
        pass

    @abstractmethod
    def create_backend(
        self, project_name: str, config: AnyBackendConfigWithCreds
    ) -> BackendRecord:
        """
        Sets up backend given backend config and returns
        text-encoded config and creds to be stored in the DB.
        It may perform backend initialization, create
        cloud resources such as networks and managed identities, and
        save additional configuration parameters.
        It does not need to duplicate validation done by `validate_config()`
        since the caller guarantees to call `validate_config()` first.
        It may perform additional validation not possible in `validate_config()`
        and raise `ServerClientError` or its subclass if config is invalid.
        """
        pass

    @abstractmethod
    def get_backend_config(
        self, record: StoredBackendRecord, include_creds: bool
    ) -> AnyBackendConfig:
        """
        Constructs `BackendConfig` to be returned in API responses.
        Project admins may need to see backend's creds. In this case `include_creds` will be `True`.
        Otherwise, no sensitive information should be included.
        """
        pass

    @abstractmethod
    def get_backend(self, record: StoredBackendRecord) -> Backend:
        """
        Returns `Backend` instance from config and creds stored in `record`.
        """
        pass


def raise_invalid_credentials_error(
    fields: Optional[List[List[str]]] = None, details: Optional[Any] = None
):
    msg = BackendInvalidCredentialsError.msg
    if details:
        msg += f": {details}"
    raise BackendInvalidCredentialsError(fields=fields, msg=msg)
