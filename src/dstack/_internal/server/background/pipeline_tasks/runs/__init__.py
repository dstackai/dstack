import asyncio
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Optional, Sequence

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, load_only, selectinload

import dstack._internal.server.background.pipeline_tasks.runs.active as active
import dstack._internal.server.background.pipeline_tasks.runs.pending as pending
import dstack._internal.server.background.pipeline_tasks.runs.terminating as terminating
from dstack._internal.core.models.runs import JobStatus, RunStatus
from dstack._internal.server.background.pipeline_tasks.base import (
    Fetcher,
    Heartbeater,
    Pipeline,
    PipelineItem,
    Worker,
    log_lock_token_changed_after_processing,
    log_lock_token_changed_on_reset,
    log_lock_token_mismatch,
    resolve_now_placeholders,
    set_processed_update_map_fields,
    set_unlock_update_map_fields,
)
from dstack._internal.server.db import get_db, get_session_ctx
from dstack._internal.server.models import InstanceModel, JobModel, ProjectModel, RunModel
from dstack._internal.server.services import events
from dstack._internal.server.services.jobs import (
    emit_job_status_change_event,
)
from dstack._internal.server.services.locking import get_locker
from dstack._internal.server.services.runs import emit_run_status_change_event
from dstack._internal.server.utils import sentry_utils
from dstack._internal.utils.common import get_current_datetime
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)

# No need to lock finished or terminating jobs since run processing does not update them.
JOB_STATUSES_EXCLUDED_FOR_LOCKING = JobStatus.finished_statuses() + [JobStatus.TERMINATING]


@dataclass
class RunPipelineItem(PipelineItem):
    status: RunStatus


class RunPipeline(Pipeline[RunPipelineItem]):
    def __init__(
        self,
        workers_num: int = 10,
        queue_lower_limit_factor: float = 0.5,
        queue_upper_limit_factor: float = 2.0,
        min_processing_interval: timedelta = timedelta(seconds=5),
        lock_timeout: timedelta = timedelta(seconds=30),
        heartbeat_trigger: timedelta = timedelta(seconds=15),
    ) -> None:
        super().__init__(
            workers_num=workers_num,
            queue_lower_limit_factor=queue_lower_limit_factor,
            queue_upper_limit_factor=queue_upper_limit_factor,
            min_processing_interval=min_processing_interval,
            lock_timeout=lock_timeout,
            heartbeat_trigger=heartbeat_trigger,
        )
        self.__heartbeater = Heartbeater[RunPipelineItem](
            model_type=RunModel,
            lock_timeout=self._lock_timeout,
            heartbeat_trigger=self._heartbeat_trigger,
        )
        self.__fetcher = RunFetcher(
            queue=self._queue,
            queue_desired_minsize=self._queue_desired_minsize,
            min_processing_interval=self._min_processing_interval,
            lock_timeout=self._lock_timeout,
            heartbeater=self._heartbeater,
        )
        self.__workers = [
            RunWorker(queue=self._queue, heartbeater=self._heartbeater)
            for _ in range(self._workers_num)
        ]

    @property
    def hint_fetch_model_name(self) -> str:
        return RunModel.__name__

    @property
    def _heartbeater(self) -> Heartbeater[RunPipelineItem]:
        return self.__heartbeater

    @property
    def _fetcher(self) -> Fetcher[RunPipelineItem]:
        return self.__fetcher

    @property
    def _workers(self) -> Sequence["RunWorker"]:
        return self.__workers


class RunFetcher(Fetcher[RunPipelineItem]):
    def __init__(
        self,
        queue: asyncio.Queue[RunPipelineItem],
        queue_desired_minsize: int,
        min_processing_interval: timedelta,
        lock_timeout: timedelta,
        heartbeater: Heartbeater[RunPipelineItem],
        queue_check_delay: float = 1.0,
    ) -> None:
        super().__init__(
            queue=queue,
            queue_desired_minsize=queue_desired_minsize,
            min_processing_interval=min_processing_interval,
            lock_timeout=lock_timeout,
            heartbeater=heartbeater,
            queue_check_delay=queue_check_delay,
        )

    @sentry_utils.instrument_named_task("pipeline_tasks.RunFetcher.fetch")
    async def fetch(self, limit: int) -> list[RunPipelineItem]:
        if limit <= 0:
            return []

        run_lock, _ = get_locker(get_db().dialect_name).get_lockset(RunModel.__tablename__)
        async with run_lock:
            async with get_session_ctx() as session:
                now = get_current_datetime()
                res = await session.execute(
                    select(RunModel)
                    .where(
                        RunModel.last_processed_at < now - self._min_processing_interval,
                        # Filter out runs that do not need processing.
                        # This is only to reduce unnecessary fetch/apply churn.
                        # Otherwise, we could fetch all active runs and filter them in the worker.
                        or_(
                            # Active non-pending runs.
                            RunModel.status.not_in(
                                RunStatus.finished_statuses() + [RunStatus.PENDING]
                            ),
                            # Retrying runs.
                            and_(
                                RunModel.status == RunStatus.PENDING,
                                RunModel.resubmission_attempt > 0,
                            ),
                            # Scheduled ready runs.
                            and_(
                                RunModel.status == RunStatus.PENDING,
                                RunModel.resubmission_attempt == 0,
                                RunModel.next_triggered_at.is_not(None),
                                RunModel.next_triggered_at < now,
                            ),
                            # Scaled-to-zero runs.
                            # Such runs cannot be scheduled, so we detect them via
                            # `next_triggered_at is None`.
                            # If scheduled services ever support downscaling to zero,
                            # this selector must be revisited.
                            and_(
                                RunModel.status == RunStatus.PENDING,
                                RunModel.resubmission_attempt == 0,
                                RunModel.next_triggered_at.is_(None),
                            ),
                        ),
                        or_(
                            RunModel.lock_expires_at.is_(None),
                            RunModel.lock_expires_at < now,
                        ),
                        or_(
                            RunModel.lock_owner.is_(None),
                            RunModel.lock_owner == RunPipeline.__name__,
                        ),
                    )
                    .order_by(RunModel.last_processed_at.asc())
                    .limit(limit)
                    .with_for_update(skip_locked=True, key_share=True, of=RunModel)
                    .options(
                        load_only(
                            RunModel.id,
                            RunModel.lock_token,
                            RunModel.lock_expires_at,
                            RunModel.status,
                        )
                    )
                )
                run_models = list(res.scalars().all())
                lock_expires_at = get_current_datetime() + self._lock_timeout
                lock_token = uuid.uuid4()
                items = []
                for run_model in run_models:
                    prev_lock_expired = run_model.lock_expires_at is not None
                    run_model.lock_expires_at = lock_expires_at
                    run_model.lock_token = lock_token
                    run_model.lock_owner = RunPipeline.__name__
                    items.append(
                        RunPipelineItem(
                            __tablename__=RunModel.__tablename__,
                            id=run_model.id,
                            lock_expires_at=lock_expires_at,
                            lock_token=lock_token,
                            prev_lock_expired=prev_lock_expired,
                            status=run_model.status,
                        )
                    )
                await session.commit()
        return items


class RunWorker(Worker[RunPipelineItem]):
    def __init__(
        self,
        queue: asyncio.Queue[RunPipelineItem],
        heartbeater: Heartbeater[RunPipelineItem],
    ) -> None:
        super().__init__(queue=queue, heartbeater=heartbeater)

    @sentry_utils.instrument_named_task("pipeline_tasks.RunWorker.process")
    async def process(self, item: RunPipelineItem):
        # Keep status dispatch explicit because run states have distinct processing
        # flows and related-row requirements. Preload, lock handling, and apply
        # stay here, while state modules own the readable business logic.
        if item.status == RunStatus.TERMINATING:
            await _process_terminating_item(item)
            return
        if item.status == RunStatus.PENDING:
            await _process_pending_item(item)
            return
        if item.status in {
            RunStatus.SUBMITTED,
            RunStatus.PROVISIONING,
            RunStatus.RUNNING,
        }:
            await _process_active_item(item)
            return

        logger.debug("Skipping run %s with unexpected status %s", item.id, item.status)


async def _process_pending_item(item: RunPipelineItem) -> None:
    await pending.process_pending_run(pending.PendingContext(run_id=item.id))


async def _process_active_item(item: RunPipelineItem) -> None:
    await active.process_active_run(
        active.ActiveContext(
            run_id=item.id,
            status=item.status,
        )
    )


async def _process_terminating_item(item: RunPipelineItem) -> None:
    async with get_session_ctx() as session:
        context = await _load_terminating_context(session=session, item=item)
        if context is None:
            return

    result = await terminating.process_terminating_run(context)
    await _apply_terminating_result(item=item, context=context, result=result)


async def _load_terminating_context(
    session: AsyncSession,
    item: RunPipelineItem,
) -> Optional[terminating.TerminatingContext]:
    run_model = await _refetch_locked_run_for_terminating(session=session, item=item)
    if run_model is None:
        log_lock_token_mismatch(logger, item)
        return None
    locked_job_models = await _lock_related_jobs(
        session=session,
        item=item,
    )
    if locked_job_models is None:
        return None
    return terminating.TerminatingContext(
        run_model=run_model,
        locked_job_models=locked_job_models,
    )


async def _refetch_locked_run_for_terminating(
    session: AsyncSession,
    item: RunPipelineItem,
) -> Optional[RunModel]:
    res = await session.execute(
        select(RunModel)
        .where(
            RunModel.id == item.id,
            RunModel.lock_token == item.lock_token,
        )
        .options(
            joinedload(RunModel.project).load_only(
                ProjectModel.id,
                ProjectModel.name,
            ),
            selectinload(RunModel.jobs)
            .joinedload(JobModel.instance)
            .joinedload(InstanceModel.project)
            .load_only(
                ProjectModel.id,
                ProjectModel.ssh_private_key,
            ),
        )
        .execution_options(populate_existing=True)
    )
    return res.unique().scalar_one_or_none()


async def _lock_related_jobs(
    session: AsyncSession,
    item: RunPipelineItem,
) -> Optional[list[JobModel]]:
    now = get_current_datetime()
    job_lock, _ = get_locker(get_db().dialect_name).get_lockset(JobModel.__tablename__)
    async with job_lock:
        res = await session.execute(
            select(JobModel)
            .where(
                JobModel.run_id == item.id,
                JobModel.status.not_in(JOB_STATUSES_EXCLUDED_FOR_LOCKING),
                or_(
                    JobModel.lock_expires_at.is_(None),
                    JobModel.lock_expires_at < now,
                ),
                or_(
                    JobModel.lock_owner.is_(None),
                    JobModel.lock_owner == RunPipeline.__name__,
                ),
            )
            .order_by(JobModel.id)
            .with_for_update(skip_locked=True, key_share=True, of=JobModel)
            .options(load_only(JobModel.id))
        )
        locked_job_models = list(res.scalars().all())
        locked_job_ids = {job_model.id for job_model in locked_job_models}

        res = await session.execute(
            select(JobModel.id).where(
                JobModel.run_id == item.id,
                JobModel.status.not_in(JOB_STATUSES_EXCLUDED_FOR_LOCKING),
            )
        )
        current_job_ids = set(res.scalars().all())
        if current_job_ids != locked_job_ids:
            logger.debug(
                "Failed to lock run %s jobs. The run will be processed later.",
                item.id,
            )
            await _reset_run_lock_for_retry(session=session, item=item)
            return None
        for job_model in locked_job_models:
            job_model.lock_expires_at = item.lock_expires_at
            job_model.lock_token = item.lock_token
            job_model.lock_owner = RunPipeline.__name__
        await session.commit()
    return locked_job_models


async def _reset_run_lock_for_retry(
    session: AsyncSession,
    item: RunPipelineItem,
) -> None:
    res = await session.execute(
        update(RunModel)
        .where(
            RunModel.id == item.id,
            RunModel.lock_token == item.lock_token,
        )
        # Keep `lock_owner` so the run remains owned by the run pipeline,
        # but unset `lock_expires_at` to retry ASAP and unset `lock_token`
        # so heartbeater can no longer update the item.
        .values(
            lock_expires_at=None,
            lock_token=None,
            last_processed_at=get_current_datetime(),
        )
        .returning(RunModel.id)
    )
    updated_ids = list(res.scalars().all())
    if len(updated_ids) == 0:
        log_lock_token_changed_on_reset(logger)


async def _apply_terminating_result(
    item: RunPipelineItem,
    context: terminating.TerminatingContext,
    result: terminating.TerminatingResult,
) -> None:
    run_model = context.run_model
    set_processed_update_map_fields(result.run_update_map)
    set_unlock_update_map_fields(result.run_update_map)

    async with get_session_ctx() as session:
        now = get_current_datetime()
        resolve_now_placeholders(result.run_update_map, now=now)
        job_update_rows = _build_terminating_job_update_rows(
            job_id_to_update_map=result.job_id_to_update_map,
            unlock_job_ids={job_model.id for job_model in context.locked_job_models},
        )
        if job_update_rows:
            resolve_now_placeholders(job_update_rows, now=now)
        res = await session.execute(
            update(RunModel)
            .where(
                RunModel.id == item.id,
                RunModel.lock_token == item.lock_token,
            )
            .values(**result.run_update_map)
            .returning(RunModel.id)
        )
        updated_run_ids = list(res.scalars().all())
        if len(updated_run_ids) == 0:
            log_lock_token_changed_after_processing(logger, item)
            await _unlock_related_jobs(
                session=session,
                item=item,
                locked_job_ids=[job_model.id for job_model in context.locked_job_models],
            )
            await session.commit()
            return

        if job_update_rows:
            await session.execute(update(JobModel), job_update_rows)

        if result.service_unregistration is not None:
            targets = [events.Target.from_model(run_model)]
            if result.service_unregistration.gateway_target is not None:
                targets.append(result.service_unregistration.gateway_target)
            events.emit(
                session,
                result.service_unregistration.event_message,
                actor=events.SystemActor(),
                targets=targets,
            )

        _emit_terminating_job_status_change_events(
            session=session,
            context=context,
            result=result,
        )
        emit_run_status_change_event(
            session=session,
            run_model=context.run_model,
            old_status=context.run_model.status,
            new_status=result.run_update_map.get("status", context.run_model.status),
        )
        await session.commit()


class _JobUpdateRow(terminating.JobUpdateMap, total=False):
    id: uuid.UUID


def _build_terminating_job_update_rows(
    job_id_to_update_map: dict[uuid.UUID, terminating.JobUpdateMap],
    unlock_job_ids: set[uuid.UUID],
) -> list[_JobUpdateRow]:
    job_update_rows = []
    for job_id in sorted(job_id_to_update_map.keys() | unlock_job_ids):
        update_row = _JobUpdateRow(id=job_id)
        job_update_map = job_id_to_update_map.get(job_id)
        if job_update_map is not None:
            for key, value in job_update_map.items():
                update_row[key] = value
        if job_id in unlock_job_ids:
            set_unlock_update_map_fields(update_row)
        set_processed_update_map_fields(update_row)
        job_update_rows.append(update_row)
    return job_update_rows


def _emit_terminating_job_status_change_events(
    session: AsyncSession,
    context: terminating.TerminatingContext,
    result: terminating.TerminatingResult,
) -> None:
    for job_model in context.run_model.jobs:
        job_update_map = result.job_id_to_update_map.get(job_model.id)
        if job_update_map is None:
            continue
        emit_job_status_change_event(
            session=session,
            job_model=job_model,
            old_status=job_model.status,
            new_status=job_update_map.get("status", job_model.status),
            termination_reason=job_update_map.get(
                "termination_reason",
                job_model.termination_reason,
            ),
            termination_reason_message=job_model.termination_reason_message,
        )


async def _unlock_related_jobs(
    session: AsyncSession,
    item: RunPipelineItem,
    locked_job_ids: Sequence[uuid.UUID],
) -> None:
    if len(locked_job_ids) == 0:
        return
    await session.execute(
        update(JobModel)
        .where(
            JobModel.id.in_(locked_job_ids),
            JobModel.lock_token == item.lock_token,
            JobModel.lock_owner == RunPipeline.__name__,
        )
        .values(
            lock_expires_at=None,
            lock_token=None,
            lock_owner=None,
        )
    )
