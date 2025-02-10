import asyncio
import heapq
from typing import Callable, Coroutine, Dict, List, Optional, Tuple, Type, Union
from uuid import UUID

from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.backends.base import Backend
from dstack._internal.core.backends.local import LocalBackend
from dstack._internal.core.errors import (
    BackendError,
    BackendInvalidCredentialsError,
    BackendNotAvailable,
    ResourceExistsError,
    ServerClientError,
)
from dstack._internal.core.models.backends import (
    AnyConfigInfoWithCreds,
    AnyConfigInfoWithCredsPartial,
    AnyConfigValues,
)
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import (
    InstanceOfferWithAvailability,
)
from dstack._internal.core.models.runs import Requirements
from dstack._internal.server.models import BackendModel, ProjectModel
from dstack._internal.server.services.backends.configurators.base import Configurator
from dstack._internal.server.settings import LOCAL_BACKEND_ENABLED
from dstack._internal.utils.common import run_async
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)

_CONFIGURATOR_CLASSES: List[Type[Configurator]] = []

try:
    from dstack._internal.server.services.backends.configurators.aws import AWSConfigurator

    _CONFIGURATOR_CLASSES.append(AWSConfigurator)
except ImportError:
    pass

try:
    from dstack._internal.server.services.backends.configurators.azure import AzureConfigurator

    _CONFIGURATOR_CLASSES.append(AzureConfigurator)
except ImportError:
    pass

try:
    from dstack._internal.server.services.backends.configurators.cudo import (
        CudoConfigurator,
    )

    _CONFIGURATOR_CLASSES.append(CudoConfigurator)
except ImportError:
    pass

try:
    from dstack._internal.server.services.backends.configurators.datacrunch import (
        DataCrunchConfigurator,
    )

    _CONFIGURATOR_CLASSES.append(DataCrunchConfigurator)
except ImportError:
    pass

try:
    from dstack._internal.server.services.backends.configurators.gcp import GCPConfigurator

    _CONFIGURATOR_CLASSES.append(GCPConfigurator)
except ImportError:
    pass

try:
    from dstack._internal.server.services.backends.configurators.kubernetes import (
        KubernetesConfigurator,
    )

    _CONFIGURATOR_CLASSES.append(KubernetesConfigurator)
except ImportError:
    pass

try:
    from dstack._internal.server.services.backends.configurators.lambdalabs import (
        LambdaConfigurator,
    )

    _CONFIGURATOR_CLASSES.append(LambdaConfigurator)
except ImportError:
    pass

try:
    from dstack._internal.server.services.backends.configurators.nebius import NebiusConfigurator

    _CONFIGURATOR_CLASSES.append(NebiusConfigurator)
except ImportError:
    pass

try:
    from dstack._internal.server.services.backends.configurators.oci import OCIConfigurator

    _CONFIGURATOR_CLASSES.append(OCIConfigurator)
except ImportError:
    pass

try:
    from dstack._internal.server.services.backends.configurators.runpod import RunpodConfigurator

    _CONFIGURATOR_CLASSES.append(RunpodConfigurator)
except ImportError:
    pass

try:
    from dstack._internal.server.services.backends.configurators.tensordock import (
        TensorDockConfigurator,
    )

    _CONFIGURATOR_CLASSES.append(TensorDockConfigurator)
except ImportError:
    pass

try:
    from dstack._internal.server.services.backends.configurators.vastai import VastAIConfigurator

    _CONFIGURATOR_CLASSES.append(VastAIConfigurator)
except ImportError:
    pass

try:
    from dstack._internal.server.services.backends.configurators.vultr import VultrConfigurator

    _CONFIGURATOR_CLASSES.append(VultrConfigurator)
except ImportError:
    pass


_BACKEND_TYPE_TO_CONFIGURATOR_CLASS_MAP = {c.TYPE: c for c in _CONFIGURATOR_CLASSES}


def register_configurator(configurator: Type[Configurator]):
    _BACKEND_TYPE_TO_CONFIGURATOR_CLASS_MAP[configurator.TYPE] = configurator


def get_configurator(backend_type: Union[BackendType, str]) -> Optional[Configurator]:
    backend_type = BackendType(backend_type)
    configurator_class = _BACKEND_TYPE_TO_CONFIGURATOR_CLASS_MAP.get(backend_type)
    if configurator_class is None:
        return None
    return configurator_class()


def list_available_backend_types() -> List[BackendType]:
    available_backend_types = []
    for configurator_class in _BACKEND_TYPE_TO_CONFIGURATOR_CLASS_MAP.values():
        available_backend_types.append(configurator_class.TYPE)
    return available_backend_types


async def get_backend_config_values(
    config: AnyConfigInfoWithCredsPartial,
) -> AnyConfigValues:
    configurator = get_configurator(config.type)
    if configurator is None:
        raise BackendNotAvailable()
    config_values = await run_async(configurator.get_config_values, config)
    return config_values


async def create_backend(
    session: AsyncSession,
    project: ProjectModel,
    config: AnyConfigInfoWithCreds,
) -> AnyConfigInfoWithCreds:
    configurator = get_configurator(config.type)
    if configurator is None:
        raise BackendNotAvailable()
    backend = await get_project_backend_by_type(project=project, backend_type=configurator.TYPE)
    if backend is not None:
        raise ResourceExistsError()
    await run_async(configurator.get_config_values, config)
    backend = await run_async(configurator.create_backend, project=project, config=config)
    session.add(backend)
    await session.commit()
    return config


async def update_backend(
    session: AsyncSession,
    project: ProjectModel,
    config: AnyConfigInfoWithCreds,
) -> AnyConfigInfoWithCreds:
    configurator = get_configurator(config.type)
    if configurator is None:
        raise BackendNotAvailable()
    backend_exists = any(configurator.TYPE == b.type for b in project.backends)
    if not backend_exists:
        raise ServerClientError("Backend does not exist")
    await run_async(configurator.get_config_values, config)
    backend = await run_async(configurator.create_backend, project=project, config=config)
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


async def get_config_info(
    project: ProjectModel,
    backend_type: BackendType,
) -> Optional[AnyConfigInfoWithCreds]:
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
            return configurator.get_config_info(backend_model, include_creds=True)
    return None


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


_BACKENDS_CACHE_LOCKS = {}
_BACKENDS_CACHE: Dict[UUID, Dict[BackendType, BackendTuple]] = {}


def _get_project_cache_lock(project_id: UUID) -> asyncio.Lock:
    return _BACKENDS_CACHE_LOCKS.setdefault(project_id, asyncio.Lock())


async def get_project_backends_with_models(project: ProjectModel) -> List[BackendTuple]:
    backends = []
    async with _get_project_cache_lock(project.id):
        key = project.id
        project_backends_cache = _BACKENDS_CACHE.setdefault(key, {})
        for backend_model in project.backends:
            cached_backend = project_backends_cache.get(backend_model.type)
            if (
                cached_backend is not None
                and cached_backend[0].config == backend_model.config
                and cached_backend[0].auth == backend_model.auth
            ):
                backends.append(cached_backend)
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
                backend = await run_async(configurator.get_backend, backend_model)
            except BackendInvalidCredentialsError:
                logger.warning(
                    "Credentials for %s backend are invalid. Backend will be ignored.",
                    backend_model.type.value,
                )
                continue
            backends.append((backend_model, backend))
            _BACKENDS_CACHE[key][backend_model.type] = (backend_model, backend)
    return backends


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


async def get_instance_offers(
    backends: List[Backend], requirements: Requirements, exclude_not_available: bool = False
) -> List[Tuple[Backend, InstanceOfferWithAvailability]]:
    """
    Returns list of instances satisfying minimal resource requirements sorted by price
    """
    logger.info("Requesting instance offers from backends: %s", [b.TYPE.value for b in backends])
    tasks = [run_async(backend.compute().get_offers_cached, requirements) for backend in backends]
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
        offers_by_backend.append(
            [
                (backend, offer)
                for offer in result
                if not exclude_not_available or offer.availability.is_available()
            ]
        )
    # Merge preserving order for every backend
    offers = heapq.merge(*offers_by_backend, key=lambda i: i[1].price)
    # Put NOT_AVAILABLE, NO_QUOTA, and BUSY instances at the end, do not sort by price
    return sorted(offers, key=lambda i: not i[1].availability.is_available())
