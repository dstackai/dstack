"""
Caches project backends and controls their lifetime.

Backends are cached per project because creating them is expensive, e.g. creating API clients
and filling offers caches. Backends may also hold resources that garbage collection does not
free, e.g. SDK clients that run background threads (see `Compute.close()`), so the cache
closes every backend explicitly once it is no longer used.

Callers use backends through leases (`lease_project_backend*()`) and must not use a backend
or its compute after the lease is released. This lets the cache know when a backend is unused:
a backend is never closed while it is leased.

A cached backend is either active or retired. New leases use only active backends.
A backend is retired if its config changes (a new backend replaces it), if it is deleted
from the project, or if it is not leased for `_BACKEND_IDLE_TTL`. A retired backend may stay
leased by operations that started before it was retired, and they keep using it until they finish.

Retired backends are closed by `close_unused_backends()`, which runs periodically, once they
are not leased. Leases never close backends: closing does not delay callers, and releasing
a lease does not await, so cancellation cannot interrupt it.

Cancelling a task that leases backends has two known problems:

* Backends are initialized and used in executor threads (`run_async()`), which cancellation
  does not interrupt. If the task is cancelled while a backend is in use, its lease is
  released while the thread still uses the backend, so a retired backend can be closed under it.
* If the task is cancelled while backends are initialized for its lease, the initialized
  backends are not cached, so they are never closed.

They are accepted because such tasks are only cancelled on server shutdown, when pipelines
cancel their workers, and backends are not closed on shutdown: the process exits anyway.
If code that leases backends is ever cancelled in other cases, e.g. by `asyncio.wait_for()`
around it, both problems can happen while the server runs. Then the lease must not be released
until the executor work finishes (e.g. shield `run_async()` and re-raise the cancellation after
it completes), and backends initialized for a cancelled lease must still be cached.
"""

import asyncio
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Callable, Coroutine, Dict, List, Optional, Tuple
from uuid import UUID

from dstack._internal.core.backends.base.backend import Backend
from dstack._internal.core.backends.base.configurator import (
    Configurator,
    StoredBackendRecord,
)
from dstack._internal.core.backends.configurators import (
    get_configurator,
)
from dstack._internal.core.errors import (
    BackendAuthError,
    BackendInvalidCredentialsError,
)
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.server.models import BackendModel, ProjectModel
from dstack._internal.server.services.backends.store import get_stored_backend_record
from dstack._internal.utils.common import run_async
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


BackendTuple = Tuple[BackendModel, Backend]
BackendSelector = Callable[
    [ProjectModel, BackendType, List[BackendTuple]],
    Coroutine[None, None, Optional[BackendTuple]],
]
"""
Selects a backend of the given type from the project backends,
see `set_select_project_backend_with_model_by_type()`.
Must return one of the given backends or `None`.
"""


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
Active and retired backends by project ID. Retired backends stay here until they are closed.
"""


def _get_project_cache_lock(project_id: UUID) -> asyncio.Lock:
    return _BACKENDS_CACHE_LOCKS.setdefault(project_id, asyncio.Lock())


@asynccontextmanager
async def lease_project_backends(project: ProjectModel) -> AsyncGenerator[List[Backend], None]:
    cached_backends = await _acquire_project_backends(project)
    try:
        yield [c.backend for c in cached_backends]
    finally:
        _release_backends(cached_backends)


_select_project_backend_with_model_by_type: Optional[BackendSelector] = None


def set_select_project_backend_with_model_by_type(func: BackendSelector):
    """
    Overrides how `lease_project_backend_by_type()` selects a backend from the project backends
    if `overrides=True` is passed. This can be used if a backend needs to be replaced with
    another backend. For example, DstackBackend in dstack Sky can be used in place of
    other backends.
    """
    global _select_project_backend_with_model_by_type
    _select_project_backend_with_model_by_type = func


@asynccontextmanager
async def lease_project_backend_by_type(
    project: ProjectModel,
    backend_type: BackendType,
    overrides: bool = False,
) -> AsyncGenerator[Optional[Backend], None]:
    async def select(backends_with_models: List[BackendTuple]) -> Optional[BackendTuple]:
        if overrides and _select_project_backend_with_model_by_type is not None:
            return await _select_project_backend_with_model_by_type(
                project, backend_type, backends_with_models
            )
        for backend_model, backend in backends_with_models:
            if backend.TYPE == backend_type:
                return backend_model, backend
        return None

    async with _lease_selected_project_backend(project, select) as backend:
        yield backend


@asynccontextmanager
async def lease_project_backend_by_id(
    project: ProjectModel, backend_id: UUID
) -> AsyncGenerator[Optional[Backend], None]:
    async def select(backends_with_models: List[BackendTuple]) -> Optional[BackendTuple]:
        for backend_model, backend in backends_with_models:
            if backend_model.id == backend_id:
                return backend_model, backend
        return None

    async with _lease_selected_project_backend(project, select) as backend:
        yield backend


async def close_unused_backends():
    """
    Retires backends that are not leased for `_BACKEND_IDLE_TTL`
    and closes retired backends that are not leased.
    """
    idle_since = time.monotonic() - _BACKEND_IDLE_TTL
    to_close: List[_CachedBackend] = []
    for project_id in list(_BACKENDS_CACHE):
        async with _get_project_cache_lock(project_id):
            project_backends = _BACKENDS_CACHE.get(project_id)
            if project_backends is None:
                continue
            for backend_type, cached_backend in list(project_backends.active.items()):
                if cached_backend.leases == 0 and cached_backend.last_used < idle_since:
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
) -> AsyncGenerator[Optional[Backend], None]:
    """
    Leases the backend chosen by `select` from the project backends.

    `select` may do I/O, so it runs outside of the cache lock: otherwise it would block
    other leases of the project and could deadlock if it leased backends itself. Then the
    selected backend could be retired and closed before it is leased, so all project backends
    are leased while `select` runs, and the ones not selected are released after it.
    They are leased without updating `last_used` so that only the selected backend
    counts as used for idle retirement.
    """
    cached_backends = await _acquire_project_backends(project, touch=False)
    selected: Optional[_CachedBackend] = None
    try:
        backend_with_model = await select([(c.model, c.backend) for c in cached_backends])
        if backend_with_model is not None:
            selected = next(
                (c for c in cached_backends if c.backend is backend_with_model[1]), None
            )
            if selected is None:
                raise ValueError("`select` must return one of the given backends")
    finally:
        _release_backends([c for c in cached_backends if c is not selected], touch=False)
    if selected is None:
        yield None
        return
    selected.last_used = time.monotonic()
    try:
        yield selected.backend
    finally:
        _release_backends([selected])


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
