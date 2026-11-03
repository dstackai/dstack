import asyncio
import json
import time
from collections.abc import AsyncIterator, Iterable, Iterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Callable, Coroutine, Dict, List, Optional, Tuple
from uuid import UUID

from pydantic import ValidationError
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
from dstack._internal.core.backends.models import (
    AnyBackendConfigWithCreds,
    AnyBackendConfigWithoutCreds,
    BackendConfigWithCreds,
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
from dstack._internal.server.services.offers import merge_offer_iterables
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


@dataclass
class _CachedBackend:
    model: BackendModel
    backend: Backend
    leases: int = 0
    last_used: float = field(default_factory=time.monotonic)


@dataclass
class _ProjectBackends:
    active: Dict[BackendType, _CachedBackend] = field(default_factory=dict)
    retired: List[_CachedBackend] = field(default_factory=list)


_BACKEND_IDLE_TTL = 300
_BACKENDS_CACHE_LOCKS: Dict[UUID, asyncio.Lock] = {}
_BACKENDS_CACHE: Dict[UUID, _ProjectBackends] = {}
"""
A backend is cached per project and used through leases (`lease_project_backend*()`).
The cache retires a backend if its config changes, if it is deleted from the project,
or if it is not leased for `_BACKEND_IDLE_TTL`. New leases use only active backends.
`close_unused_backends()` closes retired backends once they are not leased,
so callers must not use backends outside of leases.
"""


def _get_project_cache_lock(project_id: UUID) -> asyncio.Lock:
    return _BACKENDS_CACHE_LOCKS.setdefault(project_id, asyncio.Lock())


@asynccontextmanager
async def lease_project_backends_with_models(
    project: ProjectModel,
) -> AsyncIterator[List[BackendTuple]]:
    cached_backends = await _acquire_project_backends(project)
    try:
        yield [(c.model, c.backend) for c in cached_backends]
    finally:
        _release_backends(cached_backends)


@asynccontextmanager
async def lease_project_backends(project: ProjectModel) -> AsyncIterator[List[Backend]]:
    async with lease_project_backends_with_models(project) as backends_with_models:
        yield [b for _, b in backends_with_models]


_select_project_backend_with_model_by_type = None


def set_select_project_backend_with_model_by_type(
    func: Callable[
        [ProjectModel, BackendType, List[BackendTuple]],
        Coroutine[None, None, Optional[BackendTuple]],
    ],
):
    """
    Overrides how `lease_project_backend*_by_type()` select a backend from the project backends
    if `overrides=True` is passed. This can be used if a backend needs to be replaced with
    another backend. For example, DstackBackend in dstack Sky can be used in place of
    other backends.
    """
    global _select_project_backend_with_model_by_type
    _select_project_backend_with_model_by_type = func


@asynccontextmanager
async def lease_project_backend_with_model_by_type(
    project: ProjectModel,
    backend_type: BackendType,
    overrides: bool = False,
) -> AsyncIterator[Optional[BackendTuple]]:
    async def select(backends_with_models: List[BackendTuple]) -> Optional[BackendTuple]:
        if overrides and _select_project_backend_with_model_by_type is not None:
            return await _select_project_backend_with_model_by_type(
                project, backend_type, backends_with_models
            )
        for backend_model, backend in backends_with_models:
            if backend.TYPE == backend_type:
                return backend_model, backend
        return None

    async with _lease_selected_project_backend(project, select) as backend_with_model:
        yield backend_with_model


@asynccontextmanager
async def lease_project_backend_with_model_by_type_or_error(
    project: ProjectModel,
    backend_type: BackendType,
    overrides: bool = False,
) -> AsyncIterator[BackendTuple]:
    async with lease_project_backend_with_model_by_type(
        project=project, backend_type=backend_type, overrides=overrides
    ) as backend_with_model:
        if backend_with_model is None:
            raise BackendNotAvailable()
        yield backend_with_model


@asynccontextmanager
async def lease_project_backend_by_type(
    project: ProjectModel,
    backend_type: BackendType,
    overrides: bool = False,
) -> AsyncIterator[Optional[Backend]]:
    async with lease_project_backend_with_model_by_type(
        project=project, backend_type=backend_type, overrides=overrides
    ) as backend_with_model:
        yield backend_with_model[1] if backend_with_model is not None else None


@asynccontextmanager
async def lease_project_backend_by_type_or_error(
    project: ProjectModel,
    backend_type: BackendType,
    overrides: bool = False,
) -> AsyncIterator[Backend]:
    async with lease_project_backend_with_model_by_type_or_error(
        project=project, backend_type=backend_type, overrides=overrides
    ) as (_, backend):
        yield backend


@asynccontextmanager
async def lease_project_backend_with_model_by_id(
    project: ProjectModel, backend_id: UUID
) -> AsyncIterator[Optional[BackendTuple]]:
    async def select(backends_with_models: List[BackendTuple]) -> Optional[BackendTuple]:
        for backend_model, backend in backends_with_models:
            if backend_model.id == backend_id:
                return backend_model, backend
        return None

    async with _lease_selected_project_backend(project, select) as backend_with_model:
        yield backend_with_model


@asynccontextmanager
async def lease_project_backend_with_model_by_id_or_error(
    project: ProjectModel, backend_id: UUID
) -> AsyncIterator[BackendTuple]:
    async with lease_project_backend_with_model_by_id(
        project=project, backend_id=backend_id
    ) as backend_with_model:
        if backend_with_model is None:
            raise BackendNotAvailable()
        yield backend_with_model


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


async def close_unused_backends():
    """
    Retires backends that are not leased for `_BACKEND_IDLE_TTL`
    and closes retired backends that are not leased.
    """
    idle_since = time.monotonic() - _BACKEND_IDLE_TTL
    await _close_retired_backends(
        should_retire=lambda c: c.leases == 0 and c.last_used < idle_since
    )


async def close_all_backends():
    """
    Retires all backends and closes those that are not leased.
    """
    await _close_retired_backends(should_retire=lambda c: True)


async def _close_retired_backends(should_retire: Callable[[_CachedBackend], bool]):
    to_close: List[_CachedBackend] = []
    for project_id in list(_BACKENDS_CACHE):
        async with _get_project_cache_lock(project_id):
            project_backends = _BACKENDS_CACHE.get(project_id)
            if project_backends is None:
                continue
            for backend_type, cached_backend in list(project_backends.active.items()):
                if should_retire(cached_backend):
                    del project_backends.active[backend_type]
                    project_backends.retired.append(cached_backend)
            to_close.extend(c for c in project_backends.retired if c.leases == 0)
            project_backends.retired = [c for c in project_backends.retired if c.leases > 0]
            if not project_backends.active and not project_backends.retired:
                del _BACKENDS_CACHE[project_id]
    await _close_backends(to_close)


@asynccontextmanager
async def _lease_selected_project_backend(
    project: ProjectModel,
    select: Callable[[List[BackendTuple]], Coroutine[None, None, Optional[BackendTuple]]],
) -> AsyncIterator[Optional[BackendTuple]]:
    # All project backends are leased while `select` runs outside of the cache lock,
    # so that the selected backend cannot be closed in between.
    # Only the selected backend counts as used.
    cached_backends = await _acquire_project_backends(project, touch=False)
    try:
        backend_with_model = await select([(c.model, c.backend) for c in cached_backends])
    except BaseException:
        _release_backends(cached_backends, touch=False)
        raise
    selected = [
        c
        for c in cached_backends
        if backend_with_model is not None and c.backend is backend_with_model[1]
    ]
    _release_backends([c for c in cached_backends if c not in selected], touch=False)
    for c in selected:
        c.last_used = time.monotonic()
    try:
        yield backend_with_model
    finally:
        _release_backends(selected)


async def _acquire_project_backends(
    project: ProjectModel, touch: bool = True
) -> List[_CachedBackend]:
    async with _get_project_cache_lock(project.id):
        project_backends = _BACKENDS_CACHE.setdefault(project.id, _ProjectBackends())
        backend_models = {backend_model.type: backend_model for backend_model in project.backends}
        for backend_type, cached_backend in list(project_backends.active.items()):
            backend_model = backend_models.get(backend_type)
            if (
                backend_model is None
                or cached_backend.model.config != backend_model.config
                or cached_backend.model.auth != backend_model.auth
            ):
                del project_backends.active[backend_type]
                project_backends.retired.append(cached_backend)
        to_init: List[Tuple[BackendModel, Configurator, StoredBackendRecord]] = []
        for backend_model in project.backends:
            if backend_model.type in project_backends.active:
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
            backend_record = get_stored_backend_record(backend_model)
            to_init.append((backend_model, configurator, backend_record))

        if to_init:
            t0 = time.time()
            tasks = [
                _get_backend_tracked(configurator, backend_record)
                for _, configurator, backend_record in to_init
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            initialized_results = []
            for (backend_model, _, _), result in zip(to_init, results):
                if isinstance(result, BaseException):
                    if isinstance(result, (BackendInvalidCredentialsError, BackendAuthError)):
                        logger.warning(
                            "Credentials for %s backend are invalid. Backend will be ignored.",
                            backend_model.type.value,
                        )
                    else:
                        logger.error(
                            "Failed to initialize %s backend. Backend will be ignored.",
                            backend_model.type.value,
                            exc_info=result,
                        )
                else:
                    backend, duration = result
                    project_backends.active[backend_model.type] = _CachedBackend(
                        model=backend_model, backend=backend
                    )
                    initialized_results.append(f"{backend_model.type.value}={duration:.1f}s")
            logger.debug(
                "Initialized %d backends in %.1fs: %s",
                len(initialized_results),
                time.time() - t0,
                ", ".join(initialized_results),
            )

        cached_backends = list(project_backends.active.values())
        now = time.monotonic()
        for cached_backend in cached_backends:
            cached_backend.leases += 1
            if touch:
                cached_backend.last_used = now
    return cached_backends


def _release_backends(cached_backends: List[_CachedBackend], touch: bool = True):
    # Releasing does not await, so it cannot be interrupted by cancellation
    now = time.monotonic()
    for cached_backend in cached_backends:
        cached_backend.leases -= 1
        if touch:
            cached_backend.last_used = now


async def _close_backends(cached_backends: List[_CachedBackend]):
    for cached_backend, result in zip(
        cached_backends,
        await asyncio.gather(
            *(run_async(c.backend.close) for c in cached_backends), return_exceptions=True
        ),
    ):
        if isinstance(result, BaseException):
            logger.error(
                "Failed to close %s backend",
                cached_backend.model.type.value,
                exc_info=result,
            )


async def _get_backend_tracked(
    configurator: Configurator, backend_record: StoredBackendRecord
) -> Tuple[Backend, float]:
    t = time.time()
    backend = await run_async(configurator.get_backend, backend_record)
    return backend, time.time() - t


async def get_backend_offers(
    backends: List[Backend],
    requirements: Requirements,
    full_offers: bool,
    unallocated_resources: bool,
    exclude_not_available: bool = False,
) -> Iterable[Tuple[Backend, InstanceOfferWithAvailability]]:
    """
    Returns a lazy iterable of backend offers satisfying `requirements` sorted by price.
    """

    def get_filtered_offers_with_backends(
        backend: Backend,
        offers: Iterable[InstanceOfferWithAvailability],
    ) -> Iterator[Tuple[Backend, InstanceOfferWithAvailability]]:
        for offer in offers:
            if not exclude_not_available or offer.availability.is_available():
                yield (backend, offer)

    logger.debug("Requesting instance offers from backends: %s", [b.TYPE.value for b in backends])
    tasks = [
        run_async(get_offers_tracked, backend, requirements, full_offers, unallocated_resources)
        for backend in backends
    ]
    offers_by_backend: list[Iterable[tuple[Backend, InstanceOfferWithAvailability]]] = []
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
    return merge_offer_iterables(*offers_by_backend)


def check_backend_type_available(backend_type: BackendType):
    if backend_type not in list_available_backend_types():
        raise BackendNotAvailable(
            f"Backend {backend_type.value} not available."
            " Ensure that backend dependencies are installed."
            f" Available backends: {[b.value for b in list_available_backend_types()]}."
        )


def get_offers_tracked(
    backend: Backend, requirements: Requirements, full_offers: bool, unallocated_resources: bool
) -> Iterator[InstanceOfferWithAvailability]:
    start = time.time()
    res = backend.compute().get_offers(requirements, full_offers, unallocated_resources)
    duration = time.time() - start
    logger.debug("Got offers from %s in %.6fs", backend.TYPE.value, duration)
    return res
