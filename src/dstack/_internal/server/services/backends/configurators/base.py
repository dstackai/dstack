from abc import ABC, abstractmethod
from typing import Annotated, Any, List, Optional

from pydantic import Field

from dstack._internal.core.backends.base import Backend
from dstack._internal.core.errors import BackendInvalidCredentialsError
from dstack._internal.core.models.backends import (
    AnyConfigInfo,
    AnyConfigInfoWithCreds,
)
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.common import CoreModel

# Most clouds allow ~ 40-60 tags/labels per resource.
# We'll introduce our own base limit that can be customized per backend if required.
TAGS_MAX_NUM = 25


class StoredBackendRecord(CoreModel):
    config: Annotated[
        str,
        Field(description="Text-encoded non-sensitive backend config parameters (e.g. json)"),
    ]
    auth: Annotated[
        str,
        Field(
            description=(
                "Text-encoded sensitive backend config parameters (e.g. json)."
                " Configurator should not encrypt/decrypt it."
                " This is done by the caller."
            )
        ),
    ]


class Configurator(ABC):
    TYPE: BackendType

    @abstractmethod
    def validate_config(self, config: AnyConfigInfoWithCreds, default_creds_enabled: bool):
        """
        Validates backend config including backend creds and other parameters.
        Raises `ServerClientError` or its subclass if config is invalid.
        If the backend supports default creds and not `default_creds_enabled`, should raise an error.
        """
        pass

    @abstractmethod
    def create_backend(
        self, project_name: str, config: AnyConfigInfoWithCreds
    ) -> StoredBackendRecord:
        """
        Creates BackendModel given backend config and returns
        text-encoded config and creds to be stored in the db.
        It may perform backend initialization, create
        cloud resources such as networks and managed identites, and
        save additional configuration parameters.
        """
        pass

    @abstractmethod
    def get_config_info(self, record: StoredBackendRecord, include_creds: bool) -> AnyConfigInfo:
        """
        Constructs backend's ConfigInfo to be returned in API responses.
        Project admins may need to see backend's creds. In this case `include_creds` will be True.
        Otherwise, no sensitive information should be included.
        """
        pass

    @abstractmethod
    def get_backend(self, record: StoredBackendRecord) -> Backend:
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
