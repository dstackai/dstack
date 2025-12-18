import asyncio
import heapq
from collections.abc import Iterable, Iterator
from typing import Callable, Coroutine, Dict, List, Optional, Tuple
from uuid import UUID

from cachetools import TTLCache
from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.backends.base.backend import Backend
from dstack._internal.core.backends.base.configurator import (
    Configurator,
    StoredBackendRecord,
)
from dstack._internal.core.backends.configurators import (
    get_configurator,
    list_available_backend_types,
)
from dstack._internal.core.backends.local.backend import LocalBackend
from dstack._internal.core.backends.models import (
    AnyBackendConfigWithCreds,
    AnyBackendConfigWithoutCreds,
)
from dstack._internal.core.errors import (
    BackendAuthError,
    BackendError,
    BackendInvalidCredentialsError,
    BackendNotAvailable,
    ResourceExistsError,
    ResourceNotExistsError,
    ServerClientError,
)
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import (
    InstanceOfferWithAvailability,
)
from dstack._internal.core.models.runs import Requirements
from dstack._internal.server import settings
from dstack._internal.server.models import BackendModel, DecryptedString, ProjectModel
from dstack._internal.settings import LOCAL_BACKEND_ENABLED
from dstack._internal.utils.common import run_async
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


async def create_backend(
    session: AsyncSession,
    project: ProjectModel,
    config: AnyBackendConfigWithCreds,
) -> AnyBackendConfigWithCreds:
    configurator = get_configurator(config.type)
    if configurator is None:
        raise BackendNotAvailable()
    backend = await get_project_backend_by_type(project=project, backend_type=configurator.TYPE)
    if backend is not None:
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
        )
    )
    return config


async def validate_and_create_backend_model(
    project: ProjectModel,
    configurator: Configurator,
    config: AnyBackendConfigWithCreds,
) -> BackendModel:
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
    )


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


def get_stored_backend_record(backend_model: BackendModel) -> StoredBackendRecord:
    return StoredBackendRecord(
        config=backend_model.config,
        auth=backend_model.auth.get_plaintext_or_error(),
        project_id=backend_model.project_id,
        backend_id=backend_model.id,
    )


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


BackendTuple = Tuple[BackendModel, Backend]


_BACKENDS_CACHE_LOCKS: Dict[UUID, asyncio.Lock] = {}
_BACKENDS_CACHE = TTLCache[UUID, Dict[BackendType, BackendTuple]](maxsize=1000, ttl=300)


def _get_project_cache_lock(project_id: UUID) -> asyncio.Lock:
    return _BACKENDS_CACHE_LOCKS.setdefault(project_id, asyncio.Lock())


async def get_project_backends_with_models(project: ProjectModel) -> List[BackendTuple]:
    async with _get_project_cache_lock(project.id):
        key = project.id
        project_backends = _BACKENDS_CACHE.get(key, {})
        for backend_model in project.backends:
            cached_backend = project_backends.get(backend_model.type)
            if (
                cached_backend is not None
                and cached_backend[0].config == backend_model.config
                and cached_backend[0].auth == backend_model.auth
            ):
                continue
            configurator = get_configurator(backend_model.type)
            if configurator is None:
                logger.warning(
                    "Missing dependencies for %s backend. Backend will be ignored.",
                    backend_model.type.value,
                )
                continue
            if not backend_model.auth.decrypted:
                logger.warning(
                    "Failed to decrypt creds for %s backend. Backend will be ignored.",
                    backend_model.type.value,
                )
                continue
            try:
                backend_record = get_stored_backend_record(backend_model)
                backend = await run_async(configurator.get_backend, backend_record)
            except (BackendInvalidCredentialsError, BackendAuthError):
                logger.warning(
                    "Credentials for %s backend are invalid. Backend will be ignored.",
                    backend_model.type.value,
                )
                continue
            project_backends[backend_model.type] = (backend_model, backend)
        # `__setitem__()` will also expire the cache.
        # Note that there is no global cache lock so a race condition is possible:
        # one coroutine updates/re-assigns backends expired by another coroutine.
        # This is ok since the only effect is that project's cache gets restored.
        _BACKENDS_CACHE[key] = project_backends
    return list(project_backends.values())


_get_project_backend_with_model_by_type = None


def set_get_project_backend_with_model_by_type(
    func: Callable[[ProjectModel, BackendType], Coroutine[None, None, Optional[BackendTuple]]],
):
    """
    Overrides `get_project_effective_backend_with_model_by_type` with `func`.
    Then get_project_backend_* functions can pass overrides=True to call `func`
    This can be used if a backend needs to be replaced with another backend.
    For example, DstackBackend in dstack Sky can be used in place of other backends.
    """
    global _get_project_backend_with_model_by_type
    _get_project_backend_with_model_by_type = func


async def get_project_backend_with_model_by_type(
    project: ProjectModel,
    backend_type: BackendType,
    overrides: bool = False,
) -> Optional[BackendTuple]:
    if overrides and _get_project_backend_with_model_by_type is not None:
        return await _get_project_backend_with_model_by_type(project, backend_type)
    backends_with_models = await get_project_backends_with_models(project=project)
    for backend_model, backend in backends_with_models:
        if backend.TYPE == backend_type:
            return backend_model, backend
    return None


async def get_project_backend_with_model_by_type_or_error(
    project: ProjectModel,
    backend_type: BackendType,
    overrides: bool = False,
) -> BackendTuple:
    backend_with_model = await get_project_backend_with_model_by_type(
        project=project,
        backend_type=backend_type,
        overrides=overrides,
    )
    if backend_with_model is None:
        raise BackendNotAvailable()
    return backend_with_model


async def get_project_backends(project: ProjectModel) -> List[Backend]:
    backends_with_models = await get_project_backends_with_models(project)
    backends = [b for _, b in backends_with_models]
    if LOCAL_BACKEND_ENABLED:
        backends.append(LocalBackend())
    return backends


async def get_project_backend_by_type(
    project: ProjectModel,
    backend_type: BackendType,
    overrides: bool = False,
) -> Optional[Backend]:
    backend_with_model = await get_project_backend_with_model_by_type(
        project=project,
        backend_type=backend_type,
        overrides=overrides,
    )
    if backend_with_model is None:
        return None
    return backend_with_model[1]


async def get_project_backend_by_type_or_error(
    project: ProjectModel,
    backend_type: BackendType,
    overrides: bool = False,
) -> Backend:
    backend = await get_project_backend_by_type(
        project=project,
        backend_type=backend_type,
        overrides=overrides,
    )
    if backend is None:
        raise BackendNotAvailable()
    return backend


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


async def get_backend_offers(
    backends: List[Backend],
    requirements: Requirements,
    exclude_not_available: bool = False,
) -> Iterator[Tuple[Backend, InstanceOfferWithAvailability]]:
    """
    Yields backend offers satisfying `requirements` sorted by price.
    """

    def get_filtered_offers_with_backends(
        backend: Backend,
        offers: Iterable[InstanceOfferWithAvailability],
    ) -> Iterator[Tuple[Backend, InstanceOfferWithAvailability]]:
        for offer in offers:
            if not exclude_not_available or offer.availability.is_available():
                yield (backend, offer)

    logger.info("Requesting instance offers from backends: %s", [b.TYPE.value for b in backends])
    tasks = [run_async(backend.compute().get_offers, requirements) for backend in backends]
    offers_by_backend = []
    for backend, result in zip(backends, await asyncio.gather(*tasks, return_exceptions=True)):
        if isinstance(result, BackendError):
            logger.warning(
                "Failed to get offers from backend %s: %s",
                backend.TYPE,
                repr(result),
            )
            continue
        elif isinstance(result, BaseException):
            logger.error(
                "Got exception when requesting offers from backend %s",
                backend.TYPE,
                exc_info=result,
            )
            continue
        offers_by_backend.append(get_filtered_offers_with_backends(backend, result))
    # Merge preserving order for every backend.
    offers = heapq.merge(*offers_by_backend, key=lambda i: i[1].price)
    return offers


def check_backend_type_available(backend_type: BackendType):
    if backend_type not in list_available_backend_types():
        raise BackendNotAvailable(
            f"Backend {backend_type.value} not available."
            " Ensure that backend dependencies are installed."
            f" Available backends: {[b.value for b in list_available_backend_types()]}."
        )
