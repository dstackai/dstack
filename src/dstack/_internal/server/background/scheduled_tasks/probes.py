from datetime import timedelta
from functools import partial

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select, update
from sqlalchemy.orm import joinedload

from dstack._internal.core.errors import SSHError
from dstack._internal.core.models.runs import JobStatus, ProbeSpec
from dstack._internal.server.db import get_db, get_session_ctx
from dstack._internal.server.models import InstanceModel, JobModel, ProbeModel
from dstack._internal.server.services.jobs import get_job_spec
from dstack._internal.server.services.jobs.job_replica_http_client import (
    SSH_CONNECT_TIMEOUT,
    get_service_replica_client,
)
from dstack._internal.server.services.locking import get_locker
from dstack._internal.server.services.logging import fmt
from dstack._internal.utils.common import get_current_datetime
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)
BATCH_SIZE = 100
PROCESSING_OVERHEAD_TIMEOUT = timedelta(minutes=1)
PROBES_SCHEDULER = AsyncIOScheduler()


async def process_probes():
    probe_lock, probe_lockset = get_locker(get_db().dialect_name).get_lockset(
        ProbeModel.__tablename__
    )
    async with get_session_ctx() as session:
        async with probe_lock:
            res = await session.execute(
                select(ProbeModel.id)
                .where(ProbeModel.id.not_in(probe_lockset))
                .where(ProbeModel.active == True)
                .where(ProbeModel.due <= get_current_datetime())
                .order_by(ProbeModel.due.asc())
                .limit(BATCH_SIZE)
                .with_for_update(skip_locked=True, key_share=True)
            )
            probe_ids = res.unique().scalars().all()
            probe_lockset.update(probe_ids)

        try:
            # Refetch to load all attributes.
            # joinedload produces LEFT OUTER JOIN that can't be used with FOR UPDATE.
            res = await session.execute(
                select(ProbeModel)
                .where(ProbeModel.id.in_(probe_ids))
                .options(
                    joinedload(ProbeModel.job)
                    .joinedload(JobModel.instance)
                    .joinedload(InstanceModel.project)
                )
                .options(joinedload(ProbeModel.job).joinedload(JobModel.project))
                .execution_options(populate_existing=True)
            )
            probes = res.unique().scalars().all()
            for probe in probes:
                if probe.job.status != JobStatus.RUNNING:
                    probe.active = False
                else:
                    job_spec = get_job_spec(probe.job)
                    probe_spec = job_spec.probes[probe.probe_num]
                    if probe_spec.until_ready and probe.success_streak >= probe_spec.ready_after:
                        probe.active = False
                    else:
                        # Schedule the next probe execution in case this execution is interrupted
                        probe.due = get_current_datetime() + _get_probe_async_processing_timeout(
                            probe_spec
                        )
                        # Execute the probe asynchronously outside of the DB session
                        PROBES_SCHEDULER.add_job(partial(_process_probe_async, probe, probe_spec))
            await session.commit()
        finally:
            probe_lockset.difference_update(probe_ids)


async def _process_probe_async(probe: ProbeModel, probe_spec: ProbeSpec) -> None:
    start = get_current_datetime()
    logger.debug("%s: processing probe", fmt(probe))
    success = await _execute_probe(probe, probe_spec)

    async with get_session_ctx() as session:
        async with get_locker(get_db().dialect_name).lock_ctx(
            ProbeModel.__tablename__, [probe.id]
        ):
            await session.execute(
                update(ProbeModel)
                .where(ProbeModel.id == probe.id)
                .values(
                    success_streak=0 if not success else ProbeModel.success_streak + 1,
                    due=get_current_datetime() + timedelta(seconds=probe_spec.interval),
                )
            )
    logger.debug(
        "%s: probe processing took %ss",
        fmt(probe),
        (get_current_datetime() - start).total_seconds(),
    )


async def _execute_probe(probe: ProbeModel, probe_spec: ProbeSpec) -> bool:
    """
    Returns:
        Whether probe execution was successful.
    """

    try:
        async with get_service_replica_client(probe.job) as client:
            resp = await client.request(
                method=probe_spec.method,
                url="http://dstack" + probe_spec.url,
                headers=[(h.name, h.value) for h in probe_spec.headers],
                content=probe_spec.body,
                timeout=probe_spec.timeout,
                follow_redirects=False,
            )
            logger.debug("%s: probe status code: %s", fmt(probe), resp.status_code)
            return resp.is_success
    except (SSHError, httpx.RequestError) as e:
        logger.debug("%s: probe failed: %r", fmt(probe), e)
        return False


def _get_probe_async_processing_timeout(probe_spec: ProbeSpec) -> timedelta:
    return (
        timedelta(seconds=probe_spec.timeout)
        + SSH_CONNECT_TIMEOUT
        + PROCESSING_OVERHEAD_TIMEOUT  # slow db queries and other unforeseen conditions
    )
