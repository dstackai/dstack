import asyncio
import time
from collections.abc import Iterable, Iterator
from typing import List, Optional, Tuple

from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.backends.base.backend import Backend
from dstack._internal.core.backends.base.configurator import Configurator
from dstack._internal.core.backends.configurators import (
    get_configurator,
    list_available_backend_types,
)
from dstack._internal.core.backends.models import AnyBackendConfigWithCreds
from dstack._internal.core.errors import (
    BackendError,
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
from dstack._internal.server.services.backends.store import (
    get_backend_config_with_creds_from_backend_model,
    get_project_backend_model_by_type,
    get_source_backend_config_from_backend_model,
    serialize_source_backend_config,
)
from dstack._internal.server.services.offers import merge_offer_iterables
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
