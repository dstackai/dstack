import asyncio
from typing import List, Optional, Tuple, Type

from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.backends.base import Backend
from dstack._internal.core.backends.local import LocalBackend
from dstack._internal.core.errors import (
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
    InstanceAvailability,
    InstanceCandidate,
    InstanceOfferWithAvailability,
)
from dstack._internal.core.models.runs import Job
from dstack._internal.server.models import BackendModel, ProjectModel
from dstack._internal.server.services.backends.configurators.base import Configurator
from dstack._internal.server.settings import LOCAL_BACKEND_ENABLED
from dstack._internal.server.utils.common import run_async
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
    from dstack._internal.server.services.backends.configurators.gcp import GCPConfigurator

    _CONFIGURATOR_CLASSES.append(GCPConfigurator)
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
    from dstack._internal.server.services.backends.configurators.tensordock import (
        TensorDockConfigurator,
    )

    _CONFIGURATOR_CLASSES.append(TensorDockConfigurator)
except ImportError:
    pass


_BACKEND_TYPE_TO_CONFIGURATOR_CLASS_MAP = {c.TYPE: c for c in _CONFIGURATOR_CLASSES}


def get_configurator(backend_type: BackendType) -> Optional[Configurator]:
    configurator_class = _BACKEND_TYPE_TO_CONFIGURATOR_CLASS_MAP.get(backend_type)
    if configurator_class is None:
        return None
    return configurator_class()


def list_available_backend_types() -> List[BackendType]:
    available_backend_types = []
    for configurator_class in _CONFIGURATOR_CLASSES:
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
    backend = configurator.create_backend(project=project, config=config)
    session.add(backend)
    await session.commit()
    clear_backend_cache(project.name)
    return config


async def update_backend(
    session: AsyncSession,
    project: ProjectModel,
    config: AnyConfigInfoWithCreds,
) -> AnyConfigInfoWithCreds:
    configurator = get_configurator(config.type)
    if configurator is None:
        raise BackendNotAvailable()
    config_info = await get_config_info(
        project=project,
        backend_type=configurator.TYPE,
    )
    if config_info is None:
        raise ServerClientError("Backend does not exist")
    await run_async(configurator.get_config_values, config)
    backend = configurator.create_backend(project=project, config=config)
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
    clear_backend_cache(project.name)
    return config


async def get_config_info(
    project: ProjectModel,
    backend_type: BackendType,
) -> Optional[AnyConfigInfoWithCreds]:
    configurator = get_configurator(backend_type)
    if configurator is None:
        raise BackendNotAvailable()
    for b in project.backends:
        if b.type == backend_type:
            return configurator.get_config_info(b, include_creds=True)
    return None


async def delete_backends(
    session: AsyncSession,
    project: ProjectModel,
    backends_types: List[BackendType],
):
    await session.execute(
        delete(BackendModel).where(
            BackendModel.type.in_(backends_types),
            BackendModel.project_id == project.id,
        )
    )
    clear_backend_cache(project.name)


_BACKENDS_CACHE = {}

BackendTuple = Tuple[BackendModel, Backend]


async def get_project_backends_with_models(project: ProjectModel) -> List[BackendTuple]:
    key = project.name
    backends = _BACKENDS_CACHE.get(key)
    if backends is not None:
        return backends

    backends = []
    for backend_model in project.backends:
        configurator = get_configurator(backend_model.type)
        if configurator is None:
            logger.warning(
                "Missing dependencies for %s backend. Backend will be ignored.", backend_model.type
            )
            continue
        try:
            backend = await run_async(configurator.get_backend, backend_model)
        except BackendInvalidCredentialsError:
            logger.warning(
                "Credentials for %s backend are invalid. Backend will be ignored.",
                backend_model.type,
            )
            continue
        backends.append((backend_model, backend))

    _BACKENDS_CACHE[key] = backends
    return _BACKENDS_CACHE[key]


async def get_project_backends(project: ProjectModel) -> List[Backend]:
    backends_with_models = await get_project_backends_with_models(project)
    backends = [b for _, b in backends_with_models]
    if LOCAL_BACKEND_ENABLED:
        backends.append(LocalBackend())
    return backends


async def get_project_backend_by_type(
    project: ProjectModel, backend_type: BackendType
) -> Optional[Backend]:
    backends = await get_project_backends(project=project)
    for backend in backends:
        if backend.TYPE == backend_type:
            return backend
    return None


def clear_backend_cache(project_name: str):
    if project_name in _BACKENDS_CACHE:
        del _BACKENDS_CACHE[project_name]


_NOT_AVAILABLE = {InstanceAvailability.NOT_AVAILABLE, InstanceAvailability.NO_QUOTA}


async def get_instance_offers(
    backends: List[Backend], job: Job, exclude_not_available: bool = False
) -> List[Tuple[Backend, InstanceOfferWithAvailability]]:
    """
    Returns list of instances satisfying minimal resource requirements sorted by price
    """
    candidates = []
    tasks = [
        run_async(backend.compute().get_offers, job.job_spec.requirements) for backend in backends
    ]
    for backend, backend_candidates in zip(backends, await asyncio.gather(*tasks)):
        for offer in backend_candidates:
            if not exclude_not_available or offer.availability not in _NOT_AVAILABLE:
                candidates.append((backend, offer))

    # Put NOT_AVAILABLE and NO_QUOTA instances at the end
    return sorted(candidates, key=lambda i: (i[1].availability in _NOT_AVAILABLE, i[1].price))


async def get_instance_candidates(
    backends: List[Backend], job: Job, exclude_not_available: bool = False
) -> List[InstanceCandidate]:
    offers = await get_instance_offers(
        backends=backends, job=job, exclude_not_available=exclude_not_available
    )
    candidates = []
    for backend, offer in offers:
        candidate = InstanceCandidate(backend=backend.TYPE, **offer.dict())
        candidates.append(candidate)
    return candidates
