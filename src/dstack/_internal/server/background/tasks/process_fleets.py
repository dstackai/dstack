from datetime import timedelta
from typing import List

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, load_only

from dstack._internal.core.models.fleets import FleetStatus
from dstack._internal.server.db import get_db, get_session_ctx
from dstack._internal.server.models import (
    FleetModel,
    InstanceModel,
    JobModel,
    PlacementGroupModel,
    RunModel,
)
from dstack._internal.server.services.fleets import (
    get_fleet_spec,
    is_fleet_empty,
    is_fleet_in_use,
)
from dstack._internal.server.services.locking import get_locker
from dstack._internal.server.utils import sentry_utils
from dstack._internal.utils.common import get_current_datetime
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


BATCH_SIZE = 10
MIN_PROCESSING_INTERVAL = timedelta(seconds=30)


@sentry_utils.instrument_background_task
async def process_fleets():
    lock, lockset = get_locker(get_db().dialect_name).get_lockset(FleetModel.__tablename__)
    async with get_session_ctx() as session:
        async with lock:
            res = await session.execute(
                select(FleetModel)
                .where(
                    FleetModel.deleted == False,
                    FleetModel.id.not_in(lockset),
                    FleetModel.last_processed_at
                    < get_current_datetime() - MIN_PROCESSING_INTERVAL,
                )
                .options(load_only(FleetModel.id))
                .order_by(FleetModel.last_processed_at.asc())
                .limit(BATCH_SIZE)
                .with_for_update(skip_locked=True, key_share=True)
            )
            fleet_models = list(res.scalars().all())
            fleet_ids = [fm.id for fm in fleet_models]
            for fleet_id in fleet_ids:
                lockset.add(fleet_id)
        try:
            await _process_fleets(session=session, fleet_models=fleet_models)
        finally:
            lockset.difference_update(fleet_ids)


async def _process_fleets(session: AsyncSession, fleet_models: List[FleetModel]):
    fleet_ids = [fm.id for fm in fleet_models]
    # Refetch to load related attributes.
    res = await session.execute(
        select(FleetModel)
        .where(FleetModel.id.in_(fleet_ids))
        .options(joinedload(FleetModel.instances).load_only(InstanceModel.deleted))
        .options(
            joinedload(FleetModel.instances).joinedload(InstanceModel.jobs).load_only(JobModel.id)
        )
        .options(joinedload(FleetModel.runs).load_only(RunModel.status))
        .execution_options(populate_existing=True)
    )
    fleet_models = list(res.unique().scalars().all())

    deleted_fleets_ids = []
    now = get_current_datetime()
    for fleet_model in fleet_models:
        deleted = _autodelete_fleet(fleet_model)
        if deleted:
            deleted_fleets_ids.append(fleet_model.id)
        fleet_model.last_processed_at = now

    await session.execute(
        update(PlacementGroupModel)
        .where(
            PlacementGroupModel.fleet_id.in_(deleted_fleets_ids),
        )
        .values(fleet_deleted=True)
    )
    await session.commit()


def _autodelete_fleet(fleet_model: FleetModel) -> bool:
    if is_fleet_in_use(fleet_model) or not is_fleet_empty(fleet_model):
        return False

    fleet_spec = get_fleet_spec(fleet_model)
    if (
        fleet_model.status != FleetStatus.TERMINATING
        and fleet_spec.configuration.nodes is not None
        and (fleet_spec.configuration.nodes.min is None or fleet_spec.configuration.nodes.min == 0)
    ):
        # Empty fleets that allow 0 nodes should not be auto-deleted
        return False

    logger.info("Automatic cleanup of an empty fleet %s", fleet_model.name)
    fleet_model.status = FleetStatus.TERMINATED
    fleet_model.deleted = True
    logger.info("Fleet %s deleted", fleet_model.name)
    return True
