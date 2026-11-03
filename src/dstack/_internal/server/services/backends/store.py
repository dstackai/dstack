import json
from typing import Optional, Tuple

from pydantic import ValidationError

from dstack._internal.core.backends.base.configurator import (
    Configurator,
    StoredBackendRecord,
)
from dstack._internal.core.backends.models import (
    AnyBackendConfigWithCreds,
    AnyBackendConfigWithoutCreds,
    BackendConfigWithCreds,
)
from dstack._internal.core.errors import (
    BackendNotAvailable,
)
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.server.models import BackendModel, ProjectModel
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


def serialize_source_backend_config(
    config: AnyBackendConfigWithCreds,
) -> Tuple[str, Optional[str]]:
    """Split user-intent backend config into non-sensitive and sensitive JSON blobs."""
    source_config_dict = config.model_dump()
    source_auth = source_config_dict.pop("creds", None)
    source_auth_json = None if source_auth is None else json.dumps(source_auth)
    return json.dumps(source_config_dict), source_auth_json


def get_backend_config_with_creds_from_backend_model(
    configurator: Configurator,
    backend_model: BackendModel,
) -> AnyBackendConfigWithCreds:
    backend_record = get_stored_backend_record(backend_model)
    backend_config = configurator.get_backend_config_with_creds(backend_record)
    return backend_config


def get_backend_config_without_creds_from_backend_model(
    configurator: Configurator,
    backend_model: BackendModel,
) -> AnyBackendConfigWithoutCreds:
    backend_record = get_stored_backend_record(backend_model)
    backend_config = configurator.get_backend_config_without_creds(backend_record)
    return backend_config


def get_source_backend_config_from_backend_model(
    backend_model: BackendModel,
) -> Optional[AnyBackendConfigWithCreds]:
    """Reconstruct user-intent backend config from `source_config`/`source_auth`."""

    if backend_model.source_config is None:
        return None
    try:
        source_config_dict = json.loads(backend_model.source_config)
    except ValueError:
        logger.warning(
            "Failed to parse source config for %s backend. Falling back to stored config.",
            backend_model.type.value,
        )
        return None
    if backend_model.source_auth is not None:
        if not backend_model.source_auth.decrypted:
            logger.warning(
                "Failed to decrypt source creds for %s backend. Falling back to stored config.",
                backend_model.type.value,
            )
            return None
        try:
            source_config_dict["creds"] = json.loads(
                backend_model.source_auth.get_plaintext_or_error()
            )
        except ValueError:
            logger.warning(
                "Failed to parse source creds for %s backend. Falling back to stored config.",
                backend_model.type.value,
            )
            return None
    try:
        return BackendConfigWithCreds.model_validate(source_config_dict).root
    except ValidationError:
        logger.warning(
            "Failed to validate source config for %s backend. Falling back to stored config.",
            backend_model.type.value,
        )
        return None


def get_stored_backend_record(backend_model: BackendModel) -> StoredBackendRecord:
    return StoredBackendRecord(
        config=backend_model.config,
        auth=backend_model.auth.get_plaintext_or_error(),
        project_id=backend_model.project_id,
        backend_id=backend_model.id,
    )


async def get_project_backend_model_by_type(
    project: ProjectModel, backend_type: BackendType
) -> Optional[BackendModel]:
    for backend in project.backends:
        if backend.type == backend_type:
            return backend
    return None


async def get_project_backend_model_by_type_or_error(
    project: ProjectModel, backend_type: BackendType
) -> BackendModel:
    backend_model = await get_project_backend_model_by_type(
        project=project, backend_type=backend_type
    )
    if backend_model is None:
        raise BackendNotAvailable()
    return backend_model
