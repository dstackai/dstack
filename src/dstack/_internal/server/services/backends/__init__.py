from typing import List, Optional

from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.errors import BackendNotAvailable
from dstack._internal.core.models.backends import (
    AnyConfigInfoWithCreds,
    AnyConfigInfoWithCredsPartial,
    AnyConfigValues,
)
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.server.models import BackendModel, ProjectModel
from dstack._internal.server.services.backends.configurators.base import Configurator
from dstack._internal.server.utils.common import run_async

configurators_classes: List[Configurator] = []

try:
    from dstack._internal.server.services.backends.configurators.aws import AWSConfigurator

    configurators_classes.append(AWSConfigurator)
except ImportError:
    pass


backend_type_to_configurator_class_map = {c.NAME: c for c in configurators_classes}


def get_configurator(backend_type: BackendType) -> Optional[Configurator]:
    configurator_class = backend_type_to_configurator_class_map.get(backend_type)
    if configurator_class is None:
        return None
    return configurator_class()


def list_avaialble_backend_types() -> List[BackendType]:
    available_backend_types = []
    for configurator_class in configurators_classes:
        available_backend_types.append(configurator_class.NAME)
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
    await run_async(configurator.get_config_values, config)
    backend = configurator.create_backend(project=project, config=config)
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
