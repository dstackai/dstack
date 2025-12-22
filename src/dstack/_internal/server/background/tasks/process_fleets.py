from collections import defaultdict
from datetime import timedelta
from typing import List
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, load_only, selectinload

from dstack._internal.core.models.fleets import FleetSpec, FleetStatus
from dstack._internal.core.models.instances import InstanceStatus, InstanceTerminationReason
from dstack._internal.server.db import get_db, get_session_ctx
from dstack._internal.server.models import (
    FleetModel,
    InstanceModel,
    JobModel,
    PlacementGroupModel,
    RunModel,
)
from dstack._internal.server.services import events
from dstack._internal.server.services.fleets import (
    create_fleet_instance_model,
    get_fleet_spec,
    get_next_instance_num,
    is_fleet_empty,
    is_fleet_in_use,
    switch_fleet_status,
)
from dstack._internal.server.services.instances import format_instance_status_for_event
from dstack._internal.server.services.locking import get_locker
from dstack._internal.server.utils import sentry_utils
from dstack._internal.utils.common import get_current_datetime
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


BATCH_SIZE = 10
MIN_PROCESSING_INTERVAL = timedelta(seconds=30)


@sentry_utils.instrument_background_task
async def process_fleets():
    fleet_lock, fleet_lockset = get_locker(get_db().dialect_name).get_lockset(
        FleetModel.__tablename__
    )
    instance_lock, instance_lockset = get_locker(get_db().dialect_name).get_lockset(
        InstanceModel.__tablename__
    )
    async with get_session_ctx() as session:
        async with fleet_lock, instance_lock:
            res = await session.execute(
                select(FleetModel)
                .where(
                    FleetModel.deleted == False,
                    FleetModel.id.not_in(fleet_lockset),
                    FleetModel.last_processed_at
                    < get_current_datetime() - MIN_PROCESSING_INTERVAL,
                )
                .options(
                    load_only(FleetModel.id, FleetModel.name),
                    selectinload(FleetModel.instances).load_only(InstanceModel.id),
                )
                .order_by(FleetModel.last_processed_at.asc())
                .limit(BATCH_SIZE)
                .with_for_update(skip_locked=True, key_share=True)
            )
            fleet_models = list(res.scalars().unique().all())
            fleet_ids = [fm.id for fm in fleet_models]
            res = await session.execute(
                select(InstanceModel)
                .where(
                    InstanceModel.id.not_in(instance_lockset),
                    InstanceModel.fleet_id.in_(fleet_ids),
                )
                .options(load_only(InstanceModel.id, InstanceModel.fleet_id))
                .order_by(InstanceModel.id)
                .with_for_update(skip_locked=True, key_share=True)
            )
            instance_models = list(res.scalars().all())
            fleet_id_to_locked_instances = defaultdict(list)
            for instance_model in instance_models:
                fleet_id_to_locked_instances[instance_model.fleet_id].append(instance_model)
            # Process only fleets with all instances locked.
            # Other fleets won't be processed but will still be locked to avoid new transaction.
            # This should not be problematic as long as process_fleets is quick.
            fleet_models_to_process = []
            for fleet_model in fleet_models:
                if len(fleet_model.instances) == len(fleet_id_to_locked_instances[fleet_model.id]):
                    fleet_models_to_process.append(fleet_model)
                else:
                    logger.debug(
                        "Fleet %s processing will be skipped: some instance were not locked",
                        fleet_model.name,
                    )
            for fleet_id in fleet_ids:
                fleet_lockset.add(fleet_id)
            instance_ids = [im.id for im in instance_models]
            for instance_id in instance_ids:
                instance_lockset.add(instance_id)
        try:
            await _process_fleets(session=session, fleet_models=fleet_models_to_process)
        finally:
            fleet_lockset.difference_update(fleet_ids)
            instance_lockset.difference_update(instance_ids)


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
        deleted = _autodelete_fleet(session, fleet_model)
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
    changed_instances = _maintain_fleet_nodes_in_min_max_range(session, fleet_model, fleet_spec)
    if changed_instances:
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


def _maintain_fleet_nodes_in_min_max_range(
    session: AsyncSession,
    fleet_model: FleetModel,
    fleet_spec: FleetSpec,
) -> bool:
    """
    Ensures the fleet has at least `nodes.min` and at most `nodes.max` instances.
    Returns `True` if retried, added new instances, or terminated redundant instances and `False` otherwise.
    """
    assert fleet_spec.configuration.nodes is not None
    for instance in fleet_model.instances:
        # Delete terminated but not deleted instances since
        # they are going to be replaced with new pending instances.
        if instance.status == InstanceStatus.TERMINATED and not instance.deleted:
            instance.deleted = True
            instance.deleted_at = get_current_datetime()
    active_instances = [i for i in fleet_model.instances if not i.deleted]
    active_instances_num = len(active_instances)
    if active_instances_num >= fleet_spec.configuration.nodes.min:
        if (
            fleet_spec.configuration.nodes.max is None
            or active_instances_num <= fleet_spec.configuration.nodes.max
        ):
            return False
        # Fleet has more instances than allowed by nodes.max.
        # This is possible due to race conditions (e.g. provisioning jobs in a fleet concurrently)
        # or if nodes.max is updated.
        nodes_redundant = active_instances_num - fleet_spec.configuration.nodes.max
        for instance in fleet_model.instances:
            if nodes_redundant == 0:
                break
            if instance.status in [InstanceStatus.IDLE]:
                instance.status = InstanceStatus.TERMINATING
                instance.termination_reason = InstanceTerminationReason.MAX_INSTANCES_LIMIT
                instance.termination_reason_message = "Fleet has too many instances"
                nodes_redundant -= 1
                logger.info(
                    "Terminating instance %s: %s",
                    instance.name,
                    instance.termination_reason,
                )
        return True
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
        events.emit(
            session,
            (
                "Instance created to meet target fleet node count."
                f" Status: {format_instance_status_for_event(instance_model)}"
            ),
            actor=events.SystemActor(),
            targets=[events.Target.from_model(instance_model)],
        )
        active_instances.append(instance_model)
        fleet_model.instances.append(instance_model)
    logger.info("Added %s instances to fleet %s", nodes_missing, fleet_model.name)
    return True


def _autodelete_fleet(session: AsyncSession, fleet_model: FleetModel) -> bool:
    if fleet_model.project.deleted:
        # It used to be possible to delete project with active resources:
        # https://github.com/dstackai/dstack/issues/3077
        switch_fleet_status(session, fleet_model, FleetStatus.TERMINATED)
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
    switch_fleet_status(session, fleet_model, FleetStatus.TERMINATED)
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
