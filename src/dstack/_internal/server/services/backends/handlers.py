from typing import List

from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.errors import ServerClientError
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.server.models import ProjectModel
from dstack._internal.server.services.backends import delete_backends
from dstack._internal.server.services.fleets import list_project_fleet_models
from dstack._internal.server.services.volumes import list_project_volumes
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


async def delete_backends_safe(
    session: AsyncSession,
    project: ProjectModel,
    backends_types: List[BackendType],
    error: bool = True,
):
    try:
        await _check_active_instances(
            session=session,
            project=project,
            backends_types=backends_types,
            error=error,
        )
        await _check_active_volumes(
            session=session,
            project=project,
            backends_types=backends_types,
            error=error,
        )
    except ServerClientError as e:
        if error:
            raise
        logger.warning("%s", e.msg)
    await delete_backends(
        session=session,
        project=project,
        backends_types=backends_types,
    )


async def _check_active_instances(
    session: AsyncSession,
    project: ProjectModel,
    backends_types: List[BackendType],
    error: bool,
):
    fleet_models = await list_project_fleet_models(
        session=session,
        project=project,
    )
    for fleet_model in fleet_models:
        for instance in fleet_model.instances:
            if (
                instance.status.is_active()
                and instance.backend is not None
                and instance.backend in backends_types
            ):
                if error:
                    msg = (
                        f"Backend {instance.backend.value} has active instances."
                        " Delete instances before deleting the backend."
                    )
                else:
                    msg = (
                        f"Backend {instance.backend.value} has active instances."
                        " The backend will be deleted but instances may be left hanging."
                    )
                raise ServerClientError(msg)


async def _check_active_volumes(
    session: AsyncSession,
    project: ProjectModel,
    backends_types: List[BackendType],
    error: bool,
):
    volume_models = await list_project_volumes(
        session=session,
        project=project,
    )
    for volume_model in volume_models:
        if (
            volume_model.status.is_active()
            and volume_model.provisioning_data is not None
            and volume_model.provisioning_data.backend is not None
            and volume_model.provisioning_data.backend in backends_types
        ):
            if error:
                msg = (
                    f"Backend {volume_model.provisioning_data.backend.value} has active volumes."
                    " Delete volumes before deleting the backend."
                )
            else:
                msg = (
                    f"Backend {volume_model.provisioning_data.backend.value} has active volumes."
                    " The backend will be deleted but volumes may be left hanging."
                )
            raise ServerClientError(msg)
