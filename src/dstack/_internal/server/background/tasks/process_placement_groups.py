from typing import List
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from dstack._internal.core.backends.base.compute import ComputeWithPlacementGroupSupport
from dstack._internal.core.errors import PlacementGroupInUseError
from dstack._internal.server.db import get_session_ctx
from dstack._internal.server.models import PlacementGroupModel, ProjectModel
from dstack._internal.server.services import backends as backends_services
from dstack._internal.server.services.locking import get_locker
from dstack._internal.server.services.placement import placement_group_model_to_placement_group
from dstack._internal.utils.common import get_current_datetime, run_async
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


async def process_placement_groups():
    lock, lockset = get_locker().get_lockset(PlacementGroupModel.__tablename__)
    async with get_session_ctx() as session:
        async with lock:
            res = await session.execute(
                select(PlacementGroupModel)
                .where(
                    PlacementGroupModel.fleet_deleted == True,
                    PlacementGroupModel.deleted == False,
                    PlacementGroupModel.id.not_in(lockset),
                )
                .order_by(PlacementGroupModel.id)  # take locks in order
                .with_for_update(skip_locked=True)
            )
            placement_group_models = res.scalars().all()
            if len(placement_group_models) == 0:
                return
            placement_group_models_ids = [pg.id for pg in placement_group_models]
            lockset.update(placement_group_models_ids)
        try:
            await _delete_placement_groups(
                session=session,
                placement_group_models_ids=placement_group_models_ids,
            )
        finally:
            lockset.difference_update(placement_group_models_ids)


async def _delete_placement_groups(
    session: AsyncSession,
    placement_group_models_ids: List[UUID],
):
    res = await session.execute(
        select(PlacementGroupModel)
        .where(
            PlacementGroupModel.id.in_(placement_group_models_ids),
            PlacementGroupModel.deleted == False,
        )
        .options(joinedload(PlacementGroupModel.project).joinedload(ProjectModel.backends))
        .execution_options(populate_existing=True)
    )
    placement_group_models = res.unique().scalars().all()
    for pg in placement_group_models:
        await _delete_placement_group(pg)
    await session.commit()


async def _delete_placement_group(placement_group_model: PlacementGroupModel):
    logger.debug("Deleting placement group %s", placement_group_model.name)
    placement_group = placement_group_model_to_placement_group(placement_group_model)
    if placement_group.provisioning_data is None:
        logger.error(
            "Failed to delete placement group %s. provisioning_data is None.", placement_group.name
        )
        return
    backend = await backends_services.get_project_backend_by_type(
        project=placement_group_model.project,
        backend_type=placement_group.provisioning_data.backend,
    )
    if backend is None:
        logger.error(
            "Failed to delete placement group %s. Backend not available.", placement_group.name
        )
        return
    compute = backend.compute()
    assert isinstance(compute, ComputeWithPlacementGroupSupport)
    try:
        await run_async(compute.delete_placement_group, placement_group)
    except PlacementGroupInUseError:
        logger.info(
            "Placement group %s is still in use. Skipping deletion for now.", placement_group.name
        )
        return
    except Exception:
        logger.exception("Got exception when deleting placement group %s", placement_group.name)
        return

    placement_group_model.deleted = True
    placement_group_model.deleted_at = get_current_datetime()
    logger.info("Deleted placement group %s", placement_group_model.name)
