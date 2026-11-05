import json
from typing import List, Optional, Tuple

from pydantic import ValidationError
from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.backends.base.configurator import (
    Configurator,
    StoredBackendRecord,
)
from dstack._internal.core.backends.configurators import (
    get_configurator,
)
from dstack._internal.core.backends.models import (
    AnyBackendConfigWithCreds,
    AnyBackendConfigWithoutCreds,
    BackendConfigWithCreds,
)
from dstack._internal.core.errors import (
    BackendNotAvailable,
    ResourceExistsError,
    ResourceNotExistsError,
    ServerClientError,
)
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.server import settings
from dstack._internal.server.models import BackendModel, DecryptedString, ProjectModel
from dstack._internal.utils.common import run_async
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


async def validate_and_create_backend_model(
    project: ProjectModel,
    configurator: Configurator,
    config: AnyBackendConfigWithCreds,
) -> BackendModel:
    # Configurators may mutate `config` while building the effective stored backend config,
    # so capture the user-intent payload before validation/create_backend runs.
    source_config, source_auth = serialize_source_backend_config(config)
    await run_async(
        configurator.validate_config, config, default_creds_enabled=settings.DEFAULT_CREDS_ENABLED
    )
    backend_record = await run_async(
        configurator.create_backend,
        project_name=project.name,
        config=config,
    )
    return BackendModel(
        project_id=project.id,
        type=configurator.TYPE,
        config=backend_record.config,
        auth=DecryptedString(plaintext=backend_record.auth),
        source_config=source_config,
        source_auth=None if source_auth is None else DecryptedString(plaintext=source_auth),
    )


async def create_backend(
    session: AsyncSession,
    project: ProjectModel,
    config: AnyBackendConfigWithCreds,
) -> AnyBackendConfigWithCreds:
    configurator = get_configurator(config.type)
    if configurator is None:
        raise BackendNotAvailable()
    backend_exists = any(configurator.TYPE == b.type for b in project.backends)
    if backend_exists:
        raise ResourceExistsError()
    backend = await validate_and_create_backend_model(
        project=project, configurator=configurator, config=config
    )
    session.add(backend)
    await session.commit()
    return config


async def update_backend(
    session: AsyncSession,
    project: ProjectModel,
    config: AnyBackendConfigWithCreds,
) -> AnyBackendConfigWithCreds:
    configurator = get_configurator(config.type)
    if configurator is None:
        raise BackendNotAvailable()
    backend_exists = any(configurator.TYPE == b.type for b in project.backends)
    if not backend_exists:
        raise ResourceNotExistsError()
    backend = await validate_and_create_backend_model(
        project=project, configurator=configurator, config=config
    )
    # FIXME: potentially long write transaction
    await session.execute(
        update(BackendModel)
        .where(
            BackendModel.project_id == backend.project_id,
            BackendModel.type == backend.type,
        )
        .values(
            config=backend.config,
            auth=backend.auth,
            source_config=backend.source_config,
            source_auth=backend.source_auth,
        )
    )
    return config


async def get_backend_config(
    project: ProjectModel,
    backend_type: BackendType,
) -> Optional[AnyBackendConfigWithCreds]:
    configurator = get_configurator(backend_type)
    if configurator is None:
        raise BackendNotAvailable()
    for backend_model in project.backends:
        if not backend_model.auth.decrypted:
            logger.warning(
                "Failed to decrypt creds for %s backend. Backend will be ignored.",
                backend_model.type.value,
            )
            continue
        if backend_model.type == backend_type:
            return get_backend_config_with_creds_from_backend_model(configurator, backend_model)
    return None


async def get_source_backend_config(
    project: ProjectModel,
    backend_type: BackendType,
) -> Optional[AnyBackendConfigWithCreds]:
    backend_model = await get_project_backend_model_by_type(project, backend_type)
    if backend_model is None:
        return None
    return get_source_backend_config_from_backend_model(backend_model)


async def delete_backends(
    session: AsyncSession,
    project: ProjectModel,
    backends_types: List[BackendType],
):
    if BackendType.DSTACK in backends_types:
        raise ServerClientError("Cannot delete dstack backend")
    current_backends_types = set(b.type for b in project.backends)
    deleted_backends_types = current_backends_types.intersection(backends_types)
    if len(deleted_backends_types) == 0:
        return
    # FIXME: potentially long write transaction
    # Not urgent since backend deletion is a rare operation
    await session.execute(
        delete(BackendModel).where(
            BackendModel.type.in_(deleted_backends_types),
            BackendModel.project_id == project.id,
        )
    )
    logger.info(
        "Deleted backends %s in project %s",
        [b.value for b in deleted_backends_types],
        project.name,
    )
