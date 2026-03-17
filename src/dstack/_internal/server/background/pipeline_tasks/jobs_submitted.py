import asyncio
import uuid
from contextlib import AsyncExitStack
from dataclasses import dataclass
from datetime import timedelta
from typing import Optional, Sequence, Union

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, load_only

from dstack._internal.core.errors import ServerClientError
from dstack._internal.core.models.common import NetworkMode
from dstack._internal.core.models.instances import (
    InstanceOfferWithAvailability,
    InstanceStatus,
)
from dstack._internal.core.models.resources import Memory
from dstack._internal.core.models.runs import (
    Job,
    JobProvisioningData,
    JobRuntimeData,
    JobStatus,
    JobTerminationReason,
    Run,
)
from dstack._internal.core.models.volumes import Volume
from dstack._internal.server import settings
from dstack._internal.server.background.pipeline_tasks.base import (
    Fetcher,
    Heartbeater,
    Pipeline,
    PipelineItem,
    Worker,
    log_lock_token_changed_after_processing,
    log_lock_token_changed_on_reset,
    log_lock_token_mismatch,
)
from dstack._internal.server.db import get_db, get_session_ctx, is_db_sqlite, sqlite_commit
from dstack._internal.server.models import (
    FleetModel,
    InstanceModel,
    JobModel,
    ProjectModel,
    RunModel,
    UserModel,
)
from dstack._internal.server.services import events
from dstack._internal.server.services.instances import (
    format_instance_blocks_for_event,
    switch_instance_status,
)
from dstack._internal.server.services.jobs import (
    check_can_attach_job_volumes,
    find_job,
    get_job_configured_volumes,
    switch_job_status,
)
from dstack._internal.server.services.locking import get_locker
from dstack._internal.server.services.logging import fmt
from dstack._internal.server.services.runs import run_model_to_run
from dstack._internal.server.services.runs.plan import (
    find_optimal_fleet_with_offers,
    get_instance_offers_in_fleet,
    get_run_candidate_fleet_models_filters,
    select_run_candidate_fleet_models_with_filters,
)
from dstack._internal.server.utils import sentry_utils
from dstack._internal.settings import FeatureFlags
from dstack._internal.utils.common import get_current_datetime
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class JobSubmittedPipelineItem(PipelineItem):
    instance_assigned: bool


class JobSubmittedPipeline(Pipeline[JobSubmittedPipelineItem]):
    def __init__(
        self,
        workers_num: int = 20,
        queue_lower_limit_factor: float = 0.5,
        queue_upper_limit_factor: float = 2.0,
        min_processing_interval: timedelta = timedelta(seconds=4),
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
        self.__heartbeater = Heartbeater[JobSubmittedPipelineItem](
            model_type=JobModel,
            lock_timeout=self._lock_timeout,
            heartbeat_trigger=self._heartbeat_trigger,
        )
        self.__fetcher = JobSubmittedFetcher(
            queue=self._queue,
            queue_desired_minsize=self._queue_desired_minsize,
            min_processing_interval=self._min_processing_interval,
            lock_timeout=self._lock_timeout,
            heartbeater=self._heartbeater,
        )
        self.__workers = [
            JobSubmittedWorker(queue=self._queue, heartbeater=self._heartbeater)
            for _ in range(self._workers_num)
        ]

    @property
    def hint_fetch_model_name(self) -> str:
        return JobModel.__name__

    @property
    def _heartbeater(self) -> Heartbeater[JobSubmittedPipelineItem]:
        return self.__heartbeater

    @property
    def _fetcher(self) -> Fetcher[JobSubmittedPipelineItem]:
        return self.__fetcher

    @property
    def _workers(self) -> Sequence["JobSubmittedWorker"]:
        return self.__workers


class JobSubmittedFetcher(Fetcher[JobSubmittedPipelineItem]):
    def __init__(
        self,
        queue: asyncio.Queue[JobSubmittedPipelineItem],
        queue_desired_minsize: int,
        min_processing_interval: timedelta,
        lock_timeout: timedelta,
        heartbeater: Heartbeater[JobSubmittedPipelineItem],
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

    @sentry_utils.instrument_named_task("pipeline_tasks.JobSubmittedFetcher.fetch")
    async def fetch(self, limit: int) -> list[JobSubmittedPipelineItem]:
        now = get_current_datetime()
        if limit <= 0:
            return []

        job_lock, _ = get_locker(get_db().dialect_name).get_lockset(JobModel.__tablename__)
        async with job_lock:
            async with get_session_ctx() as session:
                res = await session.execute(
                    select(JobModel)
                    .join(JobModel.run)
                    .where(
                        JobModel.status == JobStatus.SUBMITTED,
                        JobModel.waiting_master_job.is_not(True),
                        or_(
                            JobModel.last_processed_at <= now - self._min_processing_interval,
                            JobModel.last_processed_at == JobModel.submitted_at,
                        ),
                        or_(
                            JobModel.lock_expires_at.is_(None),
                            JobModel.lock_expires_at < now,
                        ),
                        or_(
                            JobModel.lock_owner.is_(None),
                            JobModel.lock_owner == JobSubmittedPipeline.__name__,
                        ),
                    )
                    .order_by(RunModel.priority.desc(), JobModel.last_processed_at.asc())
                    .limit(limit)
                    .with_for_update(skip_locked=True, key_share=True, of=JobModel)
                    .options(
                        load_only(
                            JobModel.id,
                            JobModel.lock_token,
                            JobModel.lock_expires_at,
                            JobModel.instance_assigned,
                        )
                    )
                )
                job_models = list(res.scalars().all())
                lock_expires_at = get_current_datetime() + self._lock_timeout
                lock_token = uuid.uuid4()
                items = []
                for job_model in job_models:
                    prev_lock_expired = job_model.lock_expires_at is not None
                    job_model.lock_expires_at = lock_expires_at
                    job_model.lock_token = lock_token
                    job_model.lock_owner = JobSubmittedPipeline.__name__
                    items.append(
                        JobSubmittedPipelineItem(
                            __tablename__=JobModel.__tablename__,
                            id=job_model.id,
                            lock_expires_at=lock_expires_at,
                            lock_token=lock_token,
                            prev_lock_expired=prev_lock_expired,
                            instance_assigned=job_model.instance_assigned,
                        )
                    )
                await session.commit()

        return items


class JobSubmittedWorker(Worker[JobSubmittedPipelineItem]):
    def __init__(
        self,
        queue: asyncio.Queue[JobSubmittedPipelineItem],
        heartbeater: Heartbeater[JobSubmittedPipelineItem],
    ) -> None:
        super().__init__(
            queue=queue,
            heartbeater=heartbeater,
        )

    @sentry_utils.instrument_named_task("pipeline_tasks.JobSubmittedWorker.process")
    async def process(self, item: JobSubmittedPipelineItem):
        if item.instance_assigned:
            await _unlock_assigned_job_stub(item)
            return

        assignment_input = await _load_assignment_input(item)
        if assignment_input is None:
            return

        assignment = await _select_assignment(assignment_input)
        await _apply_assignment_selection(
            item=item,
            assignment_input=assignment_input,
            assignment=assignment,
        )


@dataclass
class _SubmittedJobContext:
    job_model: JobModel
    run_model: RunModel
    project: ProjectModel
    run: Run
    job: Job
    fleet_model: Optional[FleetModel]
    multinode: bool


@dataclass
class _AssignmentInput:
    context: _SubmittedJobContext
    master_job_provisioning_data: Optional[JobProvisioningData]
    volumes: list[list[Volume]]
    candidate_fleet_models: list[FleetModel]


@dataclass
class _NoFleetAssignment:
    pass


@dataclass
class _NewCapacityAssignment:
    fleet_id: uuid.UUID


@dataclass
class _ExistingInstanceAssignment:
    fleet_id: uuid.UUID


_Assignment = Union[
    _NoFleetAssignment,
    _NewCapacityAssignment,
    _ExistingInstanceAssignment,
]


async def _unlock_assigned_job_stub(item: JobSubmittedPipelineItem) -> None:
    async with get_session_ctx() as session:
        res = await session.execute(
            update(JobModel)
            .where(
                JobModel.id == item.id,
                JobModel.lock_token == item.lock_token,
            )
            .values(
                lock_expires_at=None,
                lock_token=None,
                lock_owner=None,
            )
            .returning(JobModel.id)
        )
        if res.scalar_one_or_none() is None:
            log_lock_token_changed_after_processing(
                logger, item, action="unlock", expected_outcome="unlocked"
            )


async def _load_assignment_input(item: JobSubmittedPipelineItem) -> Optional[_AssignmentInput]:
    async with get_session_ctx() as session:
        job_model = await _refetch_locked_job(session=session, item=item)
        if job_model is None:
            log_lock_token_mismatch(logger, item)
            return None

        context = await _load_submitted_job_context(session=session, job_model=job_model)
        logger.debug("%s: assignment has started", fmt(context.job_model))

        master_job_provisioning_data = await _resolve_master_job_dependency(
            session=session,
            job_model=context.job_model,
            run=context.run,
            job=context.job,
        )
        if master_job_provisioning_data is None and context.job.job_spec.job_num != 0:
            return None

        if not await _resolve_fleet_dependency(
            session=session,
            job_model=context.job_model,
            run_model=context.run_model,
            job=context.job,
        ):
            return None

        volumes = await _prepare_job_volumes(
            session=session,
            job_model=context.job_model,
            project=context.project,
            run=context.run,
            job=context.job,
        )
        if volumes is None:
            return None

        candidate_fleet_models = await _load_assignment_candidate_fleets(
            session=session,
            context=context,
        )
        return _AssignmentInput(
            context=context,
            master_job_provisioning_data=master_job_provisioning_data,
            volumes=volumes,
            candidate_fleet_models=candidate_fleet_models,
        )


async def _select_assignment(assignment_input: _AssignmentInput) -> _Assignment:
    # Getting backend offers can be slow, so fleet selection must happen outside the DB transaction.
    fleet_model, fleet_instances_with_offers, _ = await find_optimal_fleet_with_offers(
        project=assignment_input.context.project,
        fleet_models=assignment_input.candidate_fleet_models,
        run_model=assignment_input.context.run_model,
        run_spec=assignment_input.context.run.run_spec,
        job=assignment_input.context.job,
        master_job_provisioning_data=assignment_input.master_job_provisioning_data,
        volumes=assignment_input.volumes,
        exclude_not_available=True,
    )

    if fleet_model is None:
        return _NoFleetAssignment()

    if fleet_instances_with_offers:
        return _ExistingInstanceAssignment(fleet_id=fleet_model.id)

    return _NewCapacityAssignment(fleet_id=fleet_model.id)


async def _apply_assignment_selection(
    item: JobSubmittedPipelineItem,
    assignment_input: _AssignmentInput,
    assignment: _Assignment,
) -> None:
    async with get_session_ctx() as session:
        job_model = await _refetch_locked_job(session=session, item=item)
        if job_model is None:
            log_lock_token_changed_after_processing(logger, item)
            return

        if isinstance(assignment, _NoFleetAssignment):
            await _apply_no_fleet_selection(
                session=session,
                job_model=job_model,
                run=assignment_input.context.run,
            )
            return

        if isinstance(assignment, _NewCapacityAssignment):
            job_model.fleet_id = assignment.fleet_id
            job_model.instance_assigned = True
            await _mark_job_processed(session=session, job_model=job_model)
            return

        async with AsyncExitStack() as exit_stack:
            fleet_model = await _lock_assignment_fleet_for_existing_instance_assignment(
                exit_stack=exit_stack,
                session=session,
                assignment_input=assignment_input,
                fleet_id=assignment.fleet_id,
            )
            if fleet_model is None:
                await _reset_job_lock_for_retry(session=session, item=item)
                return

            # The optimal fleet was chosen from a detached snapshot. Recompute reusable
            # offers after locking the fleet instances so concurrent jobs can spread
            # across the remaining free instances instead of racing on one stale choice.
            current_instance_offers = _get_current_reusable_instance_offers(
                assignment_input=assignment_input,
                fleet_model=fleet_model,
            )
            if not current_instance_offers:
                # If the reusable offers vanished under the fleet lock, retry full
                # assignment later instead of forcing new-capacity provisioning in a
                # fleet that may no longer be optimal.
                await _reset_job_lock_for_retry(session=session, item=item)
                return

            instance_model, current_offer = current_instance_offers[0]
            _assign_instance_to_job(
                session=session,
                job_model=job_model,
                instance_model=instance_model,
                offer=current_offer,
                multinode=assignment_input.context.multinode,
            )
            await _mark_job_processed(session=session, job_model=job_model)


async def _refetch_locked_job(
    session: AsyncSession,
    item: JobSubmittedPipelineItem,
) -> Optional[JobModel]:
    res = await session.execute(
        select(JobModel)
        .where(
            JobModel.id == item.id,
            JobModel.lock_token == item.lock_token,
        )
        .execution_options(populate_existing=True)
    )
    return res.unique().scalar_one_or_none()


async def _load_submitted_job_context(
    session: AsyncSession, job_model: JobModel
) -> _SubmittedJobContext:
    res = await session.execute(
        select(JobModel)
        .where(JobModel.id == job_model.id)
        .options(
            joinedload(JobModel.fleet).selectinload(
                FleetModel.instances.and_(InstanceModel.deleted == False)
            )
        )
    )
    job_model = res.unique().scalar_one()
    res = await session.execute(
        select(RunModel)
        .where(RunModel.id == job_model.run_id)
        .options(joinedload(RunModel.project).joinedload(ProjectModel.backends))
        .options(joinedload(RunModel.user).load_only(UserModel.name))
        .options(
            joinedload(RunModel.fleet).selectinload(
                FleetModel.instances.and_(InstanceModel.deleted == False)
            )
        )
    )
    run_model = res.unique().scalar_one()
    run = run_model_to_run(run_model)
    job = find_job(run.jobs, job_model.replica_num, job_model.job_num)
    return _SubmittedJobContext(
        job_model=job_model,
        run_model=run_model,
        project=run_model.project,
        run=run,
        job=job,
        fleet_model=run_model.fleet or job_model.fleet,
        multinode=job.job_spec.jobs_per_replica > 1,
    )


async def _resolve_master_job_dependency(
    session: AsyncSession,
    job_model: JobModel,
    run: Run,
    job: Job,
) -> Optional[JobProvisioningData]:
    if job.job_spec.job_num == 0:
        return None

    master_job = find_job(run.jobs, job_model.replica_num, 0)
    if master_job.job_submissions[-1].job_provisioning_data is None:
        await _defer_submitted_job(
            session=session,
            job_model=job_model,
            log_message="waiting for master job to be provisioned",
        )
        return None

    return JobProvisioningData.__response__.parse_obj(
        master_job.job_submissions[-1].job_provisioning_data
    )


async def _resolve_fleet_dependency(
    session: AsyncSession,
    job_model: JobModel,
    run_model: RunModel,
    job: Job,
) -> bool:
    if job.job_spec.job_num == 0 and job.job_spec.replica_num == 0:
        return True
    if run_model.fleet_id is not None:
        return True

    await _defer_submitted_job(
        session=session,
        job_model=job_model,
        log_message="waiting for the run to be assigned to the fleet",
    )
    return False


async def _prepare_job_volumes(
    session: AsyncSession,
    job_model: JobModel,
    project: ProjectModel,
    run: Run,
    job: Job,
) -> Optional[list[list[Volume]]]:
    try:
        volumes = await get_job_configured_volumes(
            session=session,
            project=project,
            run_spec=run.run_spec,
            job_num=job.job_spec.job_num,
            job_spec=job.job_spec,
        )
        check_can_attach_job_volumes(volumes)
    except ServerClientError as e:
        logger.warning("%s: failed to prepare run volumes: %s", fmt(job_model), repr(e))
        await _terminate_submitted_job(
            session=session,
            job_model=job_model,
            reason=JobTerminationReason.VOLUME_ERROR,
            message=e.msg,
        )
        return None

    return volumes


async def _load_assignment_candidate_fleets(
    session: AsyncSession,
    context: _SubmittedJobContext,
) -> list[FleetModel]:
    fleet_filters, instance_filters = await get_run_candidate_fleet_models_filters(
        session=session,
        project=context.project,
        run_model=context.run_model,
        run_spec=context.run.run_spec,
    )
    (
        fleets_with_instances,
        fleets_without_instances,
    ) = await select_run_candidate_fleet_models_with_filters(
        session=session,
        fleet_filters=fleet_filters,
        instance_filters=instance_filters,
        lock_instances=False,
    )
    return fleets_with_instances + fleets_without_instances


async def _apply_no_fleet_selection(
    session: AsyncSession,
    job_model: JobModel,
    run: Run,
) -> None:
    if run.run_spec.merged_profile.fleets is not None:
        logger.debug("%s: failed to use specified fleets", fmt(job_model))
        await _terminate_submitted_job(
            session=session,
            job_model=job_model,
            reason=JobTerminationReason.FAILED_TO_START_DUE_TO_NO_CAPACITY,
            message="Failed to use specified fleets",
        )
        return

    if not FeatureFlags.AUTOCREATED_FLEETS_ENABLED:
        logger.debug("%s: no fleet found", fmt(job_model))
        await _terminate_submitted_job(
            session=session,
            job_model=job_model,
            reason=JobTerminationReason.FAILED_TO_START_DUE_TO_NO_CAPACITY,
            message=(
                "No matching fleet found. Possible reasons: "
                "https://dstack.ai/docs/guides/troubleshooting/#no-fleets"
            ),
        )
        return

    job_model.instance_assigned = True
    await _mark_job_processed(session=session, job_model=job_model)


async def _lock_assignment_fleet_for_existing_instance_assignment(
    exit_stack: AsyncExitStack,
    session: AsyncSession,
    assignment_input: _AssignmentInput,
    fleet_id: uuid.UUID,
) -> Optional[FleetModel]:
    fleet_filters, instance_filters = await get_run_candidate_fleet_models_filters(
        session=session,
        project=assignment_input.context.project,
        run_model=assignment_input.context.run_model,
        run_spec=assignment_input.context.run.run_spec,
    )
    fleet_filters.append(FleetModel.id == fleet_id)

    (
        fleets_with_instances,
        _,
    ) = await select_run_candidate_fleet_models_with_filters(
        session=session,
        fleet_filters=fleet_filters,
        instance_filters=instance_filters,
        lock_instances=True,
    )
    if not fleets_with_instances:
        return None

    instance_ids = sorted(instance.id for instance in fleets_with_instances[0].instances)
    if not instance_ids:
        return None

    if is_db_sqlite():
        await sqlite_commit(session)

    await exit_stack.enter_async_context(
        get_locker(get_db().dialect_name).lock_ctx(InstanceModel.__tablename__, instance_ids)
    )
    (
        fleets_with_locked_instances,
        _,
    ) = await select_run_candidate_fleet_models_with_filters(
        session=session,
        fleet_filters=fleet_filters,
        instance_filters=[*instance_filters, InstanceModel.id.in_(instance_ids)],
        lock_instances=True,
    )
    if not fleets_with_locked_instances:
        return None
    return fleets_with_locked_instances[0]


def _get_current_reusable_instance_offers(
    assignment_input: _AssignmentInput,
    fleet_model: FleetModel,
) -> list[tuple[InstanceModel, InstanceOfferWithAvailability]]:
    return get_instance_offers_in_fleet(
        fleet_model=fleet_model,
        run_spec=assignment_input.context.run.run_spec,
        job=assignment_input.context.job,
        master_job_provisioning_data=assignment_input.master_job_provisioning_data,
        volumes=assignment_input.volumes,
        exclude_not_available=True,
    )


def _assign_instance_to_job(
    session: AsyncSession,
    job_model: JobModel,
    instance_model: InstanceModel,
    offer: InstanceOfferWithAvailability,
    multinode: bool,
) -> None:
    job_model.fleet_id = instance_model.fleet_id
    job_model.instance_assigned = True
    job_model.instance = instance_model
    job_model.used_instance_id = instance_model.id
    job_model.job_provisioning_data = instance_model.job_provisioning_data
    job_model.job_runtime_data = _prepare_job_runtime_data(offer, multinode).json()

    switch_instance_status(session, instance_model, InstanceStatus.BUSY)
    instance_model.busy_blocks += offer.blocks
    events.emit(
        session,
        (
            "Job assigned to instance."
            f" Instance blocks: {format_instance_blocks_for_event(instance_model)}"
        ),
        actor=events.SystemActor(),
        targets=[
            events.Target.from_model(job_model),
            events.Target.from_model(instance_model),
        ],
    )


def _prepare_job_runtime_data(
    offer: InstanceOfferWithAvailability, multinode: bool
) -> JobRuntimeData:
    if offer.blocks == offer.total_blocks:
        if settings.JOB_NETWORK_MODE == settings.JobNetworkMode.FORCED_BRIDGE:
            network_mode = NetworkMode.BRIDGE
        elif settings.JOB_NETWORK_MODE == settings.JobNetworkMode.HOST_WHEN_POSSIBLE:
            network_mode = NetworkMode.HOST
        else:
            assert settings.JOB_NETWORK_MODE == settings.JobNetworkMode.HOST_FOR_MULTINODE_ONLY
            network_mode = NetworkMode.HOST if multinode else NetworkMode.BRIDGE
        return JobRuntimeData(
            network_mode=network_mode,
            offer=offer,
        )
    return JobRuntimeData(
        network_mode=NetworkMode.BRIDGE,
        offer=offer,
        cpu=offer.instance.resources.cpus,
        gpu=len(offer.instance.resources.gpus),
        memory=Memory(offer.instance.resources.memory_mib / 1024),
    )


async def _defer_submitted_job(
    session: AsyncSession,
    job_model: JobModel,
    log_message: str,
) -> None:
    logger.debug("%s: %s", fmt(job_model), log_message)
    await _mark_job_processed(session=session, job_model=job_model)


async def _terminate_submitted_job(
    session: AsyncSession,
    job_model: JobModel,
    reason: JobTerminationReason,
    message: Optional[str] = None,
) -> None:
    job_model.termination_reason = reason
    if message is not None:
        job_model.termination_reason_message = message
    switch_job_status(session, job_model, JobStatus.TERMINATING)
    await _mark_job_processed(session=session, job_model=job_model)


async def _mark_job_processed(session: AsyncSession, job_model: JobModel) -> None:
    job_model.last_processed_at = get_current_datetime()
    job_model.lock_expires_at = None
    job_model.lock_token = None
    job_model.lock_owner = None
    await session.commit()


async def _reset_job_lock_for_retry(
    session: AsyncSession,
    item: JobSubmittedPipelineItem,
) -> None:
    res = await session.execute(
        update(JobModel)
        .where(
            JobModel.id == item.id,
            JobModel.lock_token == item.lock_token,
        )
        .values(
            lock_expires_at=None,
            lock_token=None,
            last_processed_at=get_current_datetime(),
        )
        .returning(JobModel.id)
    )
    if res.scalar_one_or_none() is None:
        log_lock_token_changed_on_reset(logger)
    await session.commit()
