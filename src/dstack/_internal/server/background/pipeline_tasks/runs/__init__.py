import asyncio
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Optional, Sequence

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, contains_eager, joinedload, load_only

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
from dstack._internal.server.services.gateways import get_or_add_gateway_connection
from dstack._internal.server.services.jobs import emit_job_status_change_event
from dstack._internal.server.services.locking import get_locker
from dstack._internal.server.services.prometheus.client_metrics import run_metrics
from dstack._internal.server.services.runs import emit_run_status_change_event, get_run_spec
from dstack._internal.server.services.secrets import get_project_secrets_mapping
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
        if item.status == RunStatus.TERMINATING:
            await _process_terminating_item(item)
            return

        logger.error("Skipping run %s with unexpected status %s", item.id, item.status)


async def _process_pending_item(item: RunPipelineItem) -> None:
    async with get_session_ctx() as session:
        context = await _load_pending_context(session=session, item=item)
        if context is None:
            return

    result = await pending.process_pending_run(context)
    if result is None:
        await _apply_noop_result(
            item=item,
            locked_job_ids=context.locked_job_ids,
        )
        return

    await _apply_pending_result(item=item, context=context, result=result)


async def _load_pending_context(
    session: AsyncSession,
    item: RunPipelineItem,
) -> Optional[pending.PendingContext]:
    locked_job_ids = await _lock_related_jobs(session=session, item=item)
    if locked_job_ids is None:
        return None
    run_model = await _refetch_locked_run_for_pending(session=session, item=item)
    if run_model is None:
        log_lock_token_mismatch(logger, item)
        await _unlock_related_jobs(
            session=session,
            item=item,
            locked_job_ids=locked_job_ids,
        )
        await session.commit()
        return None
    secrets = await get_project_secrets_mapping(session=session, project=run_model.project)
    run_spec = get_run_spec(run_model)

    gateway_stats = None
    if run_spec.configuration.type == "service" and run_model.gateway_id is not None:
        _, conn = await get_or_add_gateway_connection(session, run_model.gateway_id)
        gateway_stats = await conn.get_stats(run_model.project.name, run_model.run_name)

    return pending.PendingContext(
        run_model=run_model,
        run_spec=run_spec,
        secrets=secrets,
        locked_job_ids=locked_job_ids,
        gateway_stats=gateway_stats,
    )


async def _refetch_locked_run_for_pending(
    session: AsyncSession,
    item: RunPipelineItem,
) -> Optional[RunModel]:
    latest_sq = _build_latest_submissions_subquery(item.id)
    job_alias = aliased(JobModel)
    res = await session.execute(
        select(RunModel)
        .where(
            RunModel.id == item.id,
            RunModel.lock_token == item.lock_token,
        )
        .outerjoin(latest_sq, latest_sq.c.run_id == RunModel.id)
        .outerjoin(
            job_alias,
            and_(
                job_alias.run_id == latest_sq.c.run_id,
                job_alias.replica_num == latest_sq.c.replica_num,
                job_alias.job_num == latest_sq.c.job_num,
                job_alias.submission_num == latest_sq.c.max_submission_num,
            ),
        )
        .options(
            joinedload(RunModel.project).load_only(
                ProjectModel.id,
                ProjectModel.name,
            ),
        )
        .options(contains_eager(RunModel.jobs, alias=job_alias))
        .execution_options(populate_existing=True)
    )
    return res.unique().scalar_one_or_none()


def _build_latest_submissions_subquery(run_id: uuid.UUID):
    """Subquery selecting only the latest submission per (replica_num, job_num)."""
    return (
        select(
            JobModel.run_id.label("run_id"),
            JobModel.replica_num.label("replica_num"),
            JobModel.job_num.label("job_num"),
            func.max(JobModel.submission_num).label("max_submission_num"),
        )
        .where(JobModel.run_id == run_id)
        .group_by(JobModel.run_id, JobModel.replica_num, JobModel.job_num)
        .subquery()
    )


async def _apply_pending_result(
    item: RunPipelineItem,
    context: pending.PendingContext,
    result: pending.PendingResult,
) -> None:
    set_processed_update_map_fields(result.run_update_map)
    set_unlock_update_map_fields(result.run_update_map)

    async with get_session_ctx() as session:
        now = get_current_datetime()
        resolve_now_placeholders(result.run_update_map, now=now)

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
                locked_job_ids=context.locked_job_ids,
            )
            await session.commit()
            return

        for job_model in result.new_job_models:
            session.add(job_model)
            events.emit(
                session,
                f"Job created on new submission. Status: {job_model.status.upper()}",
                actor=events.SystemActor(),
                targets=[events.Target.from_model(job_model)],
            )

        emit_run_status_change_event(
            session=session,
            run_model=context.run_model,
            old_status=context.run_model.status,
            new_status=result.run_update_map.get("status", context.run_model.status),
        )

        await _unlock_related_jobs(
            session=session,
            item=item,
            locked_job_ids=context.locked_job_ids,
        )
        await session.commit()


async def _apply_noop_result(
    item: RunPipelineItem,
    locked_job_ids: Sequence[uuid.UUID],
) -> None:
    """Unlock the run without changing state. Used when processing decides to skip."""
    async with get_session_ctx() as session:
        now = get_current_datetime()
        await session.execute(
            update(RunModel)
            .where(
                RunModel.id == item.id,
                RunModel.lock_token == item.lock_token,
            )
            .values(
                lock_expires_at=None,
                lock_token=None,
                lock_owner=None,
                last_processed_at=now,
            )
        )
        await _unlock_related_jobs(
            session=session,
            item=item,
            locked_job_ids=locked_job_ids,
        )
        await session.commit()


async def _process_active_item(item: RunPipelineItem) -> None:
    async with get_session_ctx() as session:
        load_result = await _load_active_context(session=session, item=item)
        if load_result is None:
            return
        context, _locked_job_ids = load_result

    result = await active.process_active_run(context)
    await _apply_active_result(item=item, context=context, result=result)


async def _load_active_context(
    session: AsyncSession,
    item: RunPipelineItem,
) -> Optional[tuple[active.ActiveContext, list[uuid.UUID]]]:
    """Returns None on lock mismatch (already handled).
    Returns (context, locked_job_ids) when processing should proceed."""
    locked_job_ids = await _lock_related_jobs(session=session, item=item)
    if locked_job_ids is None:
        return None
    run_model = await _refetch_locked_run_for_active(session=session, item=item)
    if run_model is None:
        log_lock_token_mismatch(logger, item)
        await _unlock_related_jobs(
            session=session,
            item=item,
            locked_job_ids=locked_job_ids,
        )
        await session.commit()
        return None
    secrets = await get_project_secrets_mapping(session=session, project=run_model.project)
    run_spec = get_run_spec(run_model)

    gateway_stats = None
    if run_spec.configuration.type == "service" and run_model.gateway_id is not None:
        _, conn = await get_or_add_gateway_connection(session, run_model.gateway_id)
        gateway_stats = await conn.get_stats(run_model.project.name, run_model.run_name)

    return (
        active.ActiveContext(
            run_model=run_model,
            run_spec=run_spec,
            secrets=secrets,
            locked_job_ids=locked_job_ids,
            gateway_stats=gateway_stats,
        ),
        locked_job_ids,
    )


async def _refetch_locked_run_for_active(
    session: AsyncSession,
    item: RunPipelineItem,
) -> Optional[RunModel]:
    latest_sq = _build_latest_submissions_subquery(item.id)
    job_alias = aliased(JobModel)
    res = await session.execute(
        select(RunModel)
        .where(
            RunModel.id == item.id,
            RunModel.lock_token == item.lock_token,
        )
        .outerjoin(latest_sq, latest_sq.c.run_id == RunModel.id)
        .outerjoin(
            job_alias,
            and_(
                job_alias.run_id == latest_sq.c.run_id,
                job_alias.replica_num == latest_sq.c.replica_num,
                job_alias.job_num == latest_sq.c.job_num,
                job_alias.submission_num == latest_sq.c.max_submission_num,
            ),
        )
        .options(
            joinedload(RunModel.project).load_only(
                ProjectModel.id,
                ProjectModel.name,
            ),
        )
        .options(
            contains_eager(RunModel.jobs, alias=job_alias)
            .joinedload(JobModel.instance)
            .load_only(InstanceModel.fleet_id),
        )
        .execution_options(populate_existing=True)
    )
    return res.unique().scalar_one_or_none()


async def _apply_active_result(
    item: RunPipelineItem,
    context: active.ActiveContext,
    result: active.ActiveResult,
) -> None:
    run_model = context.run_model
    set_processed_update_map_fields(result.run_update_map)
    set_unlock_update_map_fields(result.run_update_map)

    async with get_session_ctx() as session:
        now = get_current_datetime()
        resolve_now_placeholders(result.run_update_map, now=now)
        job_update_rows = _build_active_job_update_rows(
            job_id_to_update_map=result.job_id_to_update_map,
            unlock_job_ids=set(context.locked_job_ids),
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
                locked_job_ids=context.locked_job_ids,
            )
            await session.commit()
            return

        if job_update_rows:
            await session.execute(update(JobModel), job_update_rows)

        for job_model in result.new_job_models:
            session.add(job_model)
            events.emit(
                session,
                f"Job created on retry. Status: {job_model.status.upper()}",
                actor=events.SystemActor(),
                targets=[events.Target.from_model(job_model)],
            )

        old_status = run_model.status
        new_status = result.run_update_map.get("status", old_status)
        _emit_active_metrics(run_model, context.run_spec, old_status, new_status)

        _emit_active_job_status_change_events(
            session=session,
            context=context,
            result=result,
        )
        # Set termination_reason on the model so emit_run_status_change_event can read it.
        if "termination_reason" in result.run_update_map:
            run_model.termination_reason = result.run_update_map["termination_reason"]
        emit_run_status_change_event(
            session=session,
            run_model=run_model,
            old_status=old_status,
            new_status=new_status,
        )

        await _unlock_related_jobs(
            session=session,
            item=item,
            locked_job_ids=context.locked_job_ids,
        )
        await session.commit()


def _emit_active_metrics(
    run_model: RunModel,
    run_spec,
    old_status: RunStatus,
    new_status: RunStatus,
) -> None:
    if old_status == new_status:
        return
    project_name = run_model.project.name
    run_type = run_spec.configuration.type
    if old_status == RunStatus.SUBMITTED and new_status == RunStatus.PROVISIONING:
        duration = (get_current_datetime() - run_model.submitted_at).total_seconds()
        run_metrics.log_submit_to_provision_duration(duration, project_name, run_type)
    if new_status == RunStatus.PENDING:
        run_metrics.increment_pending_runs(project_name, run_type)


class _ActiveRunJobUpdateRow(active.ActiveRunJobUpdateMap, total=False):
    id: uuid.UUID


def _build_active_job_update_rows(
    job_id_to_update_map: dict[uuid.UUID, active.ActiveRunJobUpdateMap],
    unlock_job_ids: set[uuid.UUID],
) -> list[_ActiveRunJobUpdateRow]:
    job_update_rows = []
    for job_id in sorted(job_id_to_update_map.keys() | unlock_job_ids):
        update_row = _ActiveRunJobUpdateRow(id=job_id)
        job_update_map = job_id_to_update_map.get(job_id)
        if job_update_map is not None:
            for key, value in job_update_map.items():
                update_row[key] = value
        if job_id in unlock_job_ids:
            set_unlock_update_map_fields(update_row)
        set_processed_update_map_fields(update_row)
        job_update_rows.append(update_row)
    return job_update_rows


def _emit_active_job_status_change_events(
    session: AsyncSession,
    context: active.ActiveContext,
    result: active.ActiveResult,
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
            termination_reason_message=job_update_map.get(
                "termination_reason_message",
                job_model.termination_reason_message,
            ),
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
    locked_job_ids = await _lock_related_jobs(
        session=session,
        item=item,
    )
    if locked_job_ids is None:
        return None
    run_model = await _refetch_locked_run_for_terminating(session=session, item=item)
    if run_model is None:
        log_lock_token_mismatch(logger, item)
        await _unlock_related_jobs(
            session=session,
            item=item,
            locked_job_ids=locked_job_ids,
        )
        await session.commit()
        return None
    return terminating.TerminatingContext(
        run_model=run_model,
        locked_job_ids=locked_job_ids,
    )


async def _refetch_locked_run_for_terminating(
    session: AsyncSession,
    item: RunPipelineItem,
) -> Optional[RunModel]:
    latest_sq = _build_latest_submissions_subquery(item.id)
    job_alias = aliased(JobModel)
    res = await session.execute(
        select(RunModel)
        .where(
            RunModel.id == item.id,
            RunModel.lock_token == item.lock_token,
        )
        .outerjoin(latest_sq, latest_sq.c.run_id == RunModel.id)
        .outerjoin(
            job_alias,
            and_(
                job_alias.run_id == latest_sq.c.run_id,
                job_alias.replica_num == latest_sq.c.replica_num,
                job_alias.job_num == latest_sq.c.job_num,
                job_alias.submission_num == latest_sq.c.max_submission_num,
            ),
        )
        .options(
            joinedload(RunModel.project).load_only(
                ProjectModel.id,
                ProjectModel.name,
            ),
        )
        .options(
            contains_eager(RunModel.jobs, alias=job_alias)
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
) -> Optional[list[uuid.UUID]]:
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
    return [jm.id for jm in locked_job_models]


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
            unlock_job_ids=set(context.locked_job_ids),
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
            # The only side-effects are runner stop signal and service deregistration,
            # and they are idempotent, so no need for cleanup.
            log_lock_token_changed_after_processing(logger, item)
            await _unlock_related_jobs(
                session=session,
                item=item,
                locked_job_ids=context.locked_job_ids,
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


class _TerminatingRunJobUpdateRow(terminating.TerminatingRunJobUpdateMap, total=False):
    id: uuid.UUID


def _build_terminating_job_update_rows(
    job_id_to_update_map: dict[uuid.UUID, terminating.TerminatingRunJobUpdateMap],
    unlock_job_ids: set[uuid.UUID],
) -> list[_TerminatingRunJobUpdateRow]:
    job_update_rows = []
    for job_id in sorted(job_id_to_update_map.keys() | unlock_job_ids):
        update_row = _TerminatingRunJobUpdateRow(id=job_id)
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
