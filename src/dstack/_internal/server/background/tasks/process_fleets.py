from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from dstack._internal.core.models.fleets import FleetStatus
from dstack._internal.server.db import get_session_ctx
from dstack._internal.server.models import FleetModel
from dstack._internal.server.services.fleets import (
    is_fleet_empty,
    is_fleet_in_use,
)
from dstack._internal.server.services.locking import get_locker
from dstack._internal.server.services.placement import schedule_fleet_placement_groups_deletion
from dstack._internal.utils.common import get_current_datetime
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


async def process_fleets():
    lock, lockset = get_locker().get_lockset(FleetModel.__tablename__)
    async with get_session_ctx() as session:
        async with lock:
            res = await session.execute(
                select(FleetModel)
                .where(
                    FleetModel.deleted == False,
                    FleetModel.id.not_in(lockset),
                )
                .order_by(FleetModel.last_processed_at.asc())
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            fleet_model = res.scalar()
            if fleet_model is None:
                return
            lockset.add(fleet_model.id)
        try:
            fleet_model_id = fleet_model.id
            await _process_fleet(session=session, fleet_model=fleet_model)
        finally:
            lockset.difference_update([fleet_model_id])


async def _process_fleet(session: AsyncSession, fleet_model: FleetModel):
    # Refetch to load related attributes.
    # joinedload produces LEFT OUTER JOIN that can't be used with FOR UPDATE.
    res = await session.execute(
        select(FleetModel)
        .where(FleetModel.id == fleet_model.id)
        .options(joinedload(FleetModel.project))
        .options(joinedload(FleetModel.instances))
        .options(joinedload(FleetModel.runs))
        .execution_options(populate_existing=True)
    )
    fleet_model = res.unique().scalar_one()
    await _autodelete_fleet(session=session, fleet_model=fleet_model)


async def _autodelete_fleet(session: AsyncSession, fleet_model: FleetModel):
    # Currently all empty fleets are autodeleted.
    # TODO: If fleets with `nodes: 0..` are supported, their deletion should be skipped.
    if is_fleet_in_use(fleet_model) or not is_fleet_empty(fleet_model):
        fleet_model.last_processed_at = get_current_datetime()
        await session.commit()
        return

    logger.info("Automatic cleanup of an empty fleet %s", fleet_model.name)
    fleet_model.status = FleetStatus.TERMINATED
    fleet_model.deleted = True
    fleet_model.last_processed_at = get_current_datetime()
    await schedule_fleet_placement_groups_deletion(session=session, fleet_id=fleet_model.id)
    await session.commit()
    logger.info("Fleet %s deleted", fleet_model.name)
