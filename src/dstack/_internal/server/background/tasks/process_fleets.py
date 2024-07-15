from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from dstack._internal.server.db import get_session_ctx
from dstack._internal.server.models import FleetModel
from dstack._internal.server.services.fleets import (
    PROCESSING_FLEETS_IDS,
    PROCESSING_FLEETS_LOCK,
    is_fleet_empty,
    is_fleet_in_use,
)
from dstack._internal.utils.common import get_current_datetime
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


async def process_empty_fleets():
    async with get_session_ctx() as session:
        async with PROCESSING_FLEETS_LOCK:
            res = await session.execute(
                select(FleetModel)
                .where(
                    FleetModel.deleted == False,
                    FleetModel.id.not_in(PROCESSING_FLEETS_IDS),
                )
                .order_by(FleetModel.last_processed_at.asc())
                .limit(1)
            )
            fleet_model = res.scalar()
            if fleet_model is None:
                return

            PROCESSING_FLEETS_IDS.add(fleet_model.id)

    try:
        await _process_fleet(fleet_id=fleet_model.id)
    finally:
        PROCESSING_FLEETS_IDS.remove(fleet_model.id)


async def _process_fleet(fleet_id: UUID):
    async with get_session_ctx() as session:
        res = await session.execute(
            select(FleetModel)
            .where(FleetModel.id == fleet_id)
            .options(joinedload(FleetModel.instances))
            .options(joinedload(FleetModel.runs))
        )
        fleet_model = res.unique().scalar_one()
        await _process_empty_fleet(
            session=session,
            fleet_model=fleet_model,
        )


async def _process_empty_fleet(session: AsyncSession, fleet_model: FleetModel):
    if is_fleet_in_use(fleet_model) or not is_fleet_empty(fleet_model):
        fleet_model.last_processed_at = get_current_datetime()
        await session.commit()
        return

    logger.info("Automatic cleanup of an empty fleet %s", fleet_model.name)

    fleet_model.deleted = True
    fleet_model.last_processed_at = get_current_datetime()
    await session.commit()

    logger.info("Fleet %s deleted", fleet_model.name)
