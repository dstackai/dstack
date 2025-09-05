from datetime import timedelta
from typing import List
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, load_only

from dstack._internal.core.models.fleets import FleetSpec, FleetStatus
from dstack._internal.core.models.instances import InstanceStatus
from dstack._internal.server.db import get_db, get_session_ctx
from dstack._internal.server.models import (
    FleetModel,
    InstanceModel,
    JobModel,
    PlacementGroupModel,
    RunModel,
)
from dstack._internal.server.services.fleets import (
    create_fleet_instance_model,
    get_fleet_spec,
    get_next_instance_num,
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
        .options(
            joinedload(FleetModel.instances).joinedload(InstanceModel.jobs).load_only(JobModel.id),
            joinedload(FleetModel.project),
        )
        .options(joinedload(FleetModel.runs).load_only(RunModel.status))
        .execution_options(populate_existing=True)
    )
    fleet_models = list(res.unique().scalars().all())

    # TODO: Drop fleets auto-deletion after dropping fleets auto-creation.
    deleted_fleets_ids = []
    for fleet_model in fleet_models:
        _consolidate_fleet_state_with_spec(session, fleet_model)
        deleted = _autodelete_fleet(fleet_model)
        if deleted:
            deleted_fleets_ids.append(fleet_model.id)
        fleet_model.last_processed_at = get_current_datetime()
    await _update_deleted_fleets_placement_groups(session, deleted_fleets_ids)
    await session.commit()


def _consolidate_fleet_state_with_spec(session: AsyncSession, fleet_model: FleetModel):
    if fleet_model.status == FleetStatus.TERMINATING:
        return
    fleet_spec = get_fleet_spec(fleet_model)
    if fleet_spec.configuration.nodes is None or fleet_spec.autocreated:
        # Only explicitly created cloud fleets are consolidated.
        return
    if not _is_fleet_ready_for_consolidation(fleet_model):
        return
    added_instances = _maintain_fleet_nodes_min(session, fleet_model, fleet_spec)
    if added_instances:
        fleet_model.consolidation_attempt += 1
    else:
        # The fleet is already consolidated or consolidation is in progress.
        # We reset consolidation_attempt in both cases for simplicity.
        # The second case does not need reset but is ok to do since
        # it means consolidation is longer than delay, so it won't happen too often.
        # TODO: Reset consolidation_attempt on fleet in-place update.
        fleet_model.consolidation_attempt = 0
    fleet_model.last_consolidated_at = get_current_datetime()


def _is_fleet_ready_for_consolidation(fleet_model: FleetModel) -> bool:
    consolidation_retry_delay = _get_consolidation_retry_delay(fleet_model.consolidation_attempt)
    last_consolidated_at = fleet_model.last_consolidated_at or fleet_model.last_processed_at
    duration_since_last_consolidation = get_current_datetime() - last_consolidated_at
    return duration_since_last_consolidation >= consolidation_retry_delay


# We use exponentially increasing consolidation retry delays so that
# consolidation does not happen too often. In particular, this prevents
# retrying instance provisioning constantly in case of no offers.
# TODO: Adjust delays.
_CONSOLIDATION_RETRY_DELAYS = [
    timedelta(seconds=30),
    timedelta(minutes=1),
    timedelta(minutes=2),
    timedelta(minutes=5),
    timedelta(minutes=10),
]


def _get_consolidation_retry_delay(consolidation_attempt: int) -> timedelta:
    if consolidation_attempt < len(_CONSOLIDATION_RETRY_DELAYS):
        return _CONSOLIDATION_RETRY_DELAYS[consolidation_attempt]
    return _CONSOLIDATION_RETRY_DELAYS[-1]


def _maintain_fleet_nodes_min(
    session: AsyncSession,
    fleet_model: FleetModel,
    fleet_spec: FleetSpec,
) -> bool:
    """
    Ensures the fleet has at least `nodes.min` instances.
    Returns `True` if retried or added new instances and `False` otherwise.
    """
    assert fleet_spec.configuration.nodes is not None
    for instance in fleet_model.instances:
        # Delete terminated but not deleted instances since
        # they are going to be replaced with new pending instances.
        if instance.status == InstanceStatus.TERMINATED and not instance.deleted:
            # It's safe to modify instances without instance lock since
            # no other task modifies already terminated instances.
            instance.deleted = True
            instance.deleted_at = get_current_datetime()
    active_instances = [i for i in fleet_model.instances if not i.deleted]
    active_instances_num = len(active_instances)
    if active_instances_num >= fleet_spec.configuration.nodes.min:
        return False
    nodes_missing = fleet_spec.configuration.nodes.min - active_instances_num
    for i in range(nodes_missing):
        instance_model = create_fleet_instance_model(
            session=session,
            project=fleet_model.project,
            # TODO: Store fleet.user and pass it instead of the project owner.
            username=fleet_model.project.owner.name,
            spec=fleet_spec,
            instance_num=get_next_instance_num({i.instance_num for i in active_instances}),
        )
        active_instances.append(instance_model)
        fleet_model.instances.append(instance_model)
    logger.info("Added %s instances to fleet %s", nodes_missing, fleet_model.name)
    return True


def _autodelete_fleet(fleet_model: FleetModel) -> bool:
    if fleet_model.project.deleted:
        # It used to be possible to delete project with active resources:
        # https://github.com/dstackai/dstack/issues/3077
        fleet_model.status = FleetStatus.TERMINATED
        fleet_model.deleted = True
        logger.info("Fleet %s deleted due to deleted project", fleet_model.name)
        return True

    if is_fleet_in_use(fleet_model) or not is_fleet_empty(fleet_model):
        return False

    fleet_spec = get_fleet_spec(fleet_model)
    if (
        fleet_model.status != FleetStatus.TERMINATING
        and fleet_spec.configuration.nodes is not None
        and fleet_spec.configuration.nodes.min == 0
    ):
        # Empty fleets that allow 0 nodes should not be auto-deleted
        return False

    logger.info("Automatic cleanup of an empty fleet %s", fleet_model.name)
    fleet_model.status = FleetStatus.TERMINATED
    fleet_model.deleted = True
    logger.info("Fleet %s deleted", fleet_model.name)
    return True


async def _update_deleted_fleets_placement_groups(session: AsyncSession, fleets_ids: list[UUID]):
    if len(fleets_ids) == 0:
        return
    await session.execute(
        update(PlacementGroupModel)
        .where(
            PlacementGroupModel.fleet_id.in_(fleets_ids),
        )
        .values(fleet_deleted=True)
    )
