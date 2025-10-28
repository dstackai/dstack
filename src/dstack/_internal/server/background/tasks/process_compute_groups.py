import asyncio
import datetime
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, load_only

from dstack._internal.core.backends.base.compute import ComputeWithGroupProvisioningSupport
from dstack._internal.core.errors import BackendError
from dstack._internal.core.models.compute_groups import ComputeGroupStatus
from dstack._internal.core.models.instances import InstanceStatus
from dstack._internal.server.db import get_db, get_session_ctx
from dstack._internal.server.models import (
    ComputeGroupModel,
    ProjectModel,
)
from dstack._internal.server.services import backends as backends_services
from dstack._internal.server.services.compute_groups import compute_group_model_to_compute_group
from dstack._internal.server.services.locking import get_locker
from dstack._internal.server.utils import sentry_utils
from dstack._internal.utils.common import get_current_datetime, run_async
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


MIN_PROCESSING_INTERVAL = timedelta(seconds=30)

TERMINATION_RETRY_TIMEOUT = timedelta(seconds=60)
TERMINATION_RETRY_MAX_DURATION = timedelta(minutes=15)


async def process_compute_groups(batch_size: int = 1):
    tasks = []
    for _ in range(batch_size):
        tasks.append(_process_next_compute_group())
    await asyncio.gather(*tasks)


@sentry_utils.instrument_background_task
async def _process_next_compute_group():
    lock, lockset = get_locker(get_db().dialect_name).get_lockset(ComputeGroupModel.__tablename__)
    async with get_session_ctx() as session:
        async with lock:
            res = await session.execute(
                select(ComputeGroupModel)
                .where(
                    ComputeGroupModel.deleted == False,
                    ComputeGroupModel.id.not_in(lockset),
                    ComputeGroupModel.last_processed_at
                    < get_current_datetime() - MIN_PROCESSING_INTERVAL,
                )
                .options(load_only(ComputeGroupModel.id))
                .order_by(ComputeGroupModel.last_processed_at.asc())
                .limit(1)
                .with_for_update(skip_locked=True, key_share=True)
            )
            compute_group_model = res.scalar()
            if compute_group_model is None:
                return
            compute_group_model_id = compute_group_model.id
            lockset.add(compute_group_model_id)
        try:
            await _process_compute_group(
                session=session,
                compute_group_model=compute_group_model,
            )
        finally:
            lockset.difference_update([compute_group_model_id])


async def _process_compute_group(session: AsyncSession, compute_group_model: ComputeGroupModel):
    # Refetch to load related attributes.
    res = await session.execute(
        select(ComputeGroupModel)
        .where(ComputeGroupModel.id == compute_group_model.id)
        .options(
            joinedload(ComputeGroupModel.instances),
            joinedload(ComputeGroupModel.project).joinedload(ProjectModel.backends),
        )
        .execution_options(populate_existing=True)
    )
    compute_group_model = res.unique().scalar_one()
    if all(i.status == InstanceStatus.TERMINATING for i in compute_group_model.instances):
        await _terminate_compute_group(compute_group_model)
    compute_group_model.last_processed_at = get_current_datetime()
    await session.commit()


async def _terminate_compute_group(compute_group_model: ComputeGroupModel) -> None:
    if (
        compute_group_model.last_termination_retry_at is not None
        and _next_termination_retry_at(compute_group_model) > get_current_datetime()
    ):
        return
    compute_group = compute_group_model_to_compute_group(compute_group_model)
    cgpd = compute_group.provisioning_data
    backend = await backends_services.get_project_backend_by_type(
        project=compute_group_model.project,
        backend_type=cgpd.backend,
    )
    if backend is None:
        logger.error(
            "Failed to terminate compute group %s. Backend %s not available.",
            compute_group.name,
            cgpd.backend,
        )
    else:
        logger.debug("Terminating compute group %s", compute_group.name)
        compute = backend.compute()
        assert isinstance(compute, ComputeWithGroupProvisioningSupport)
        try:
            await run_async(
                compute.terminate_compute_group,
                compute_group,
            )
        except Exception as e:
            if compute_group_model.first_termination_retry_at is None:
                compute_group_model.first_termination_retry_at = get_current_datetime()
            compute_group_model.last_termination_retry_at = get_current_datetime()
            if _next_termination_retry_at(compute_group_model) < _get_termination_deadline(
                compute_group_model
            ):
                logger.warning(
                    "Failed to terminate compute group %s. Will retry. Error: %r",
                    compute_group.name,
                    e,
                    exc_info=not isinstance(e, BackendError),
                )
                return
            logger.error(
                "Failed all attempts to terminate compute group %s."
                " Please terminate it manually to avoid unexpected charges."
                " Error: %r",
                compute_group.name,
                e,
                exc_info=not isinstance(e, BackendError),
            )

    compute_group_model.deleted = True
    compute_group_model.deleted_at = get_current_datetime()
    compute_group_model.status = ComputeGroupStatus.TERMINATED
    # Terminating instances belonging to a compute group are locked implicitly
    # by locking the compute group.
    for instance_model in compute_group_model.instances:
        instance_model.deleted = True
        instance_model.deleted_at = get_current_datetime()
        instance_model.finished_at = get_current_datetime()
        instance_model.status = InstanceStatus.TERMINATED
    logger.info(
        "Terminated compute group %s",
        compute_group.name,
    )


def _next_termination_retry_at(compute_group_model: ComputeGroupModel) -> datetime.datetime:
    assert compute_group_model.last_termination_retry_at is not None
    return compute_group_model.last_termination_retry_at + TERMINATION_RETRY_TIMEOUT


def _get_termination_deadline(compute_group_model: ComputeGroupModel) -> datetime.datetime:
    assert compute_group_model.first_termination_retry_at is not None
    return compute_group_model.first_termination_retry_at + TERMINATION_RETRY_MAX_DURATION
