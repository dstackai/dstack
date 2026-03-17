import asyncio
import uuid
from contextlib import AsyncExitStack
from dataclasses import dataclass
from datetime import timedelta
from typing import Optional, Sequence, Union

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, load_only

from dstack._internal.core.backends.base.compute import (
    ComputeWithGroupProvisioningSupport,
    ComputeWithPlacementGroupSupport,
    ComputeWithVolumeSupport,
)
from dstack._internal.core.backends.base.models import JobConfiguration
from dstack._internal.core.backends.features import (
    BACKENDS_WITH_GROUP_PROVISIONING_SUPPORT,
    BACKENDS_WITH_PLACEMENT_GROUPS_SUPPORT,
)
from dstack._internal.core.errors import BackendError, ServerClientError
from dstack._internal.core.models.common import NetworkMode
from dstack._internal.core.models.compute_groups import (
    ComputeGroupProvisioningData,
    ComputeGroupStatus,
)
from dstack._internal.core.models.fleets import (
    FleetConfiguration,
    FleetNodesSpec,
    FleetSpec,
    FleetStatus,
    InstanceGroupPlacement,
)
from dstack._internal.core.models.instances import (
    InstanceOfferWithAvailability,
    InstanceStatus,
)
from dstack._internal.core.models.profiles import (
    DEFAULT_RUN_TERMINATION_IDLE_TIME,
    CreationPolicy,
    Profile,
    TerminationPolicy,
)
from dstack._internal.core.models.resources import Memory
from dstack._internal.core.models.runs import (
    Job,
    JobProvisioningData,
    JobRuntimeData,
    JobStatus,
    JobTerminationReason,
    Requirements,
    Run,
)
from dstack._internal.core.models.volumes import Volume
from dstack._internal.core.services.profiles import get_termination
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
from dstack._internal.server.db import (
    get_db,
    get_session_ctx,
    is_db_postgres,
    is_db_sqlite,
    sqlite_commit,
)
from dstack._internal.server.models import (
    ComputeGroupModel,
    FleetModel,
    InstanceModel,
    JobModel,
    PlacementGroupModel,
    ProjectModel,
    RunModel,
    UserModel,
    VolumeAttachmentModel,
    VolumeModel,
)
from dstack._internal.server.services import events
from dstack._internal.server.services.backends import get_project_backend_by_type_or_error
from dstack._internal.server.services.fleets import (
    check_can_create_new_cloud_instance_in_fleet,
    generate_fleet_name,
    get_fleet_master_instance_provisioning_data,
    get_fleet_spec,
    get_next_instance_num,
    is_cloud_cluster,
)
from dstack._internal.server.services.instances import (
    format_instance_blocks_for_event,
    get_instance_offer,
    get_instance_provisioning_data,
    switch_instance_status,
)
from dstack._internal.server.services.jobs import (
    check_can_attach_job_volumes,
    find_job,
    find_jobs,
    get_job_configured_volume_models,
    get_job_configured_volumes,
    get_job_runtime_data,
    is_master_job,
    is_multinode_job,
    switch_job_status,
)
from dstack._internal.server.services.locking import get_locker, string_to_lock_id
from dstack._internal.server.services.logging import fmt
from dstack._internal.server.services.offers import (
    get_instance_offer_with_restricted_az,
    get_offers_by_requirements,
)
from dstack._internal.server.services.placement import (
    find_or_create_suitable_placement_group,
    get_fleet_placement_group_models,
    get_placement_group_model_for_job,
    placement_group_model_to_placement_group_optional,
)
from dstack._internal.server.services.runs import run_model_to_run
from dstack._internal.server.services.runs.plan import (
    find_optimal_fleet_with_offers,
    get_instance_offers_in_fleet,
    get_run_candidate_fleet_models_filters,
    get_run_profile_and_requirements_in_fleet,
    select_run_candidate_fleet_models_with_filters,
)
from dstack._internal.server.services.runs.spec import (
    check_run_spec_requires_instance_mounts,
    get_nodes_required_num,
)
from dstack._internal.server.services.volumes import volume_model_to_volume
from dstack._internal.server.utils import sentry_utils
from dstack._internal.settings import FeatureFlags
from dstack._internal.utils.common import get_current_datetime, get_or_error, run_async
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
        context = await _load_process_context(item=item)
        if context is None:
            log_lock_token_mismatch(logger, item)
            return

        if context.job_model.instance_assigned:
            logger.debug("%s: provisioning has started", fmt(context.job_model))
            provisioning = await _process_provisioning(context=context)
            await _apply_provisioning_result(
                item=item,
                provisioning=provisioning,
            )
            return

        logger.debug("%s: assignment has started", fmt(context.job_model))
        assignment = await _process_assignment(context=context)
        await _apply_assignment_result(
            item=item,
            context=context,
            assignment=assignment,
        )


@dataclass
class _SubmittedJobContext:
    job_model: JobModel
    run_model: RunModel
    project: ProjectModel
    run: Run
    job: Job
    jobs_to_provision: list[Job]
    replica_jobs: list[Job]
    replica_job_model_ids: list[uuid.UUID]
    fleet_model: Optional[FleetModel]
    multinode: bool


@dataclass
class _PreparedJobVolumes:
    volume_model_ids: list[list[uuid.UUID]]
    volumes: list[list[Volume]]


@dataclass
class _ProcessedPreconditions:
    master_job_provisioning_data: Optional[JobProvisioningData]
    prepared_job_volumes: _PreparedJobVolumes


@dataclass
class _DeferSubmittedJobResult:
    log_message: str


@dataclass
class _TerminateSubmittedJobResult:
    reason: JobTerminationReason
    message: Optional[str] = None


@dataclass
class _VolumeAttachmentPayload:
    volume_id: uuid.UUID
    attachment_data: str
    volume_name: str


@dataclass
class _VolumeAttachmentResult:
    attachments: list[_VolumeAttachmentPayload]
    termination_message: Optional[str] = None


@dataclass
class _NoFleetAssignment:
    pass


@dataclass
class _ExistingInstanceAssignment:
    fleet_id: uuid.UUID
    master_job_provisioning_data: Optional[JobProvisioningData]
    volumes: list[list[Volume]]


@dataclass
class _NewCapacityAssignment:
    fleet_id: uuid.UUID


_AssignmentResult = Union[
    _DeferSubmittedJobResult,
    _TerminateSubmittedJobResult,
    _NoFleetAssignment,
    _NewCapacityAssignment,
    _ExistingInstanceAssignment,
]


@dataclass
class _ExistingInstanceProvisioning:
    instance_id: uuid.UUID
    volume_attachment_result: _VolumeAttachmentResult


@dataclass
class _ProvisionNewCapacityResult:
    provisioning_data: Union[JobProvisioningData, ComputeGroupProvisioningData]
    offer: InstanceOfferWithAvailability
    effective_profile: Profile
    new_placement_group_models: list[PlacementGroupModel]


@dataclass
class _NewCapacityProvisioning:
    provisioning_data: Union[JobProvisioningData, ComputeGroupProvisioningData]
    offer: InstanceOfferWithAvailability
    effective_profile: Profile
    created_fleet_model: Optional[FleetModel]
    new_placement_group_models: list[PlacementGroupModel]
    volume_attachment_result: Optional[_VolumeAttachmentResult]


_ProvisioningResult = Union[
    _DeferSubmittedJobResult,
    _TerminateSubmittedJobResult,
    _ExistingInstanceProvisioning,
    _NewCapacityProvisioning,
]


async def _load_process_context(item: JobSubmittedPipelineItem) -> Optional[_SubmittedJobContext]:
    async with get_session_ctx() as session:
        job_model = await _refetch_locked_job(session=session, item=item)
        if job_model is None:
            return None
        return await _load_submitted_job_context(session=session, job_model=job_model)


async def _process_assignment(context: _SubmittedJobContext) -> _AssignmentResult:
    preconditions = await _process_preconditions(context=context)
    if not isinstance(preconditions, _ProcessedPreconditions):
        return preconditions

    candidate_fleet_models = await _load_assignment_candidate_fleets(context=context)
    return await _select_assignment(
        context=context,
        preconditions=preconditions,
        candidate_fleet_models=candidate_fleet_models,
    )


async def _select_assignment(
    context: _SubmittedJobContext,
    preconditions: _ProcessedPreconditions,
    candidate_fleet_models: list[FleetModel],
) -> _AssignmentResult:
    # Getting backend offers can be slow, so fleet selection must happen outside the DB transaction.
    fleet_model, fleet_instances_with_offers, _ = await find_optimal_fleet_with_offers(
        project=context.project,
        fleet_models=candidate_fleet_models,
        run_model=context.run_model,
        run_spec=context.run.run_spec,
        job=context.job,
        master_job_provisioning_data=preconditions.master_job_provisioning_data,
        volumes=preconditions.prepared_job_volumes.volumes,
        exclude_not_available=True,
    )

    if fleet_model is None:
        return _NoFleetAssignment()

    if fleet_instances_with_offers:
        return _ExistingInstanceAssignment(
            fleet_id=fleet_model.id,
            master_job_provisioning_data=preconditions.master_job_provisioning_data,
            volumes=preconditions.prepared_job_volumes.volumes,
        )

    return _NewCapacityAssignment(fleet_id=fleet_model.id)


async def _apply_assignment_result(
    item: JobSubmittedPipelineItem,
    context: _SubmittedJobContext,
    assignment: _AssignmentResult,
) -> None:
    async with get_session_ctx() as session:
        job_model = await _refetch_locked_job(session=session, item=item)
        if job_model is None:
            log_lock_token_changed_after_processing(logger, item)
            return

        if isinstance(assignment, _DeferSubmittedJobResult):
            await _defer_submitted_job(
                session=session,
                job_model=job_model,
                log_message=assignment.log_message,
            )
            return

        if isinstance(assignment, _TerminateSubmittedJobResult):
            await _terminate_submitted_job(
                session=session,
                job_model=job_model,
                reason=assignment.reason,
                message=assignment.message,
            )
            return

        if isinstance(assignment, _NoFleetAssignment):
            await _apply_no_fleet_selection(
                session=session,
                job_model=job_model,
                run=context.run,
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
                context=context,
                fleet_id=assignment.fleet_id,
            )
            if fleet_model is None:
                await _reset_job_lock_for_retry(session=session, item=item)
                return

            # The optimal fleet was chosen from a detached snapshot. Recompute reusable
            # offers after locking the fleet instances so concurrent jobs can spread
            # across the remaining free instances instead of racing on one stale choice.
            current_instance_offers = _get_current_reusable_instance_offers(
                context=context,
                assignment=assignment,
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
                multinode=context.multinode,
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
        .options(joinedload(JobModel.instance))
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
        .options(joinedload(RunModel.jobs))
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
    replica_jobs = find_jobs(run.jobs, replica_num=job_model.replica_num)
    return _SubmittedJobContext(
        job_model=job_model,
        run_model=run_model,
        project=run_model.project,
        run=run,
        job=job,
        jobs_to_provision=_select_jobs_to_provision(job, replica_jobs, job_model),
        replica_jobs=replica_jobs,
        replica_job_model_ids=_get_job_model_ids_for_jobs(run_model.jobs, replica_jobs),
        fleet_model=run_model.fleet or job_model.fleet,
        multinode=job.job_spec.jobs_per_replica > 1,
    )


def _get_job_model_ids_for_jobs(
    job_models: list[JobModel],
    jobs: list[Job],
) -> list[uuid.UUID]:
    id_to_job_model_map = {job_model.id: job_model for job_model in job_models}
    return [id_to_job_model_map[job.job_submissions[-1].id].id for job in jobs]


def _get_job_models_for_jobs(
    job_models: list[JobModel],
    jobs: list[Job],
) -> list[JobModel]:
    id_to_job_model_map = {job_model.id: job_model for job_model in job_models}
    return [id_to_job_model_map[job.job_submissions[-1].id] for job in jobs]


def _get_job_models_by_ids(
    job_models: list[JobModel],
    job_model_ids: list[uuid.UUID],
) -> list[JobModel]:
    id_to_job_model_map = {job_model.id: job_model for job_model in job_models}
    return [id_to_job_model_map[job_model_id] for job_model_id in job_model_ids]


async def _process_preconditions(
    context: _SubmittedJobContext,
) -> Union[
    _ProcessedPreconditions,
    _DeferSubmittedJobResult,
    _TerminateSubmittedJobResult,
]:
    master_job_provisioning_data = _get_master_job_provisioning_data(context=context)
    if context.job.job_spec.job_num != 0 and master_job_provisioning_data is None:
        return _DeferSubmittedJobResult(log_message="waiting for master job to be provisioned")

    if _should_wait_for_run_fleet_assignment(context=context):
        return _DeferSubmittedJobResult(
            log_message="waiting for the run to be assigned to the fleet"
        )

    prepared_job_volumes = await _prepare_job_volumes(context=context)
    if isinstance(prepared_job_volumes, _TerminateSubmittedJobResult):
        return prepared_job_volumes

    return _ProcessedPreconditions(
        master_job_provisioning_data=master_job_provisioning_data,
        prepared_job_volumes=prepared_job_volumes,
    )


def _get_master_job_provisioning_data(
    context: _SubmittedJobContext,
) -> Optional[JobProvisioningData]:
    if context.job.job_spec.job_num == 0:
        return None

    master_job = find_job(context.run.jobs, context.job_model.replica_num, 0)
    if master_job.job_submissions[-1].job_provisioning_data is None:
        return None

    return JobProvisioningData.__response__.parse_obj(
        master_job.job_submissions[-1].job_provisioning_data
    )


def _should_wait_for_run_fleet_assignment(context: _SubmittedJobContext) -> bool:
    if context.job.job_spec.job_num == 0 and context.job.job_spec.replica_num == 0:
        return False
    return context.run_model.fleet_id is None


async def _prepare_job_volumes(
    context: _SubmittedJobContext,
) -> Union[_PreparedJobVolumes, _TerminateSubmittedJobResult]:
    async with get_session_ctx() as session:
        try:
            volume_models = await get_job_configured_volume_models(
                session=session,
                project=context.project,
                run_spec=context.run.run_spec,
                job_num=context.job.job_spec.job_num,
                job_spec=context.job.job_spec,
            )
            volumes = await get_job_configured_volumes(
                session=session,
                project=context.project,
                run_spec=context.run.run_spec,
                job_num=context.job.job_spec.job_num,
                job_spec=context.job.job_spec,
            )
            check_can_attach_job_volumes(volumes)
        except ServerClientError as e:
            logger.warning(
                "%s: failed to prepare run volumes: %s", fmt(context.job_model), repr(e)
            )
            return _TerminateSubmittedJobResult(
                reason=JobTerminationReason.VOLUME_ERROR,
                message=e.msg,
            )

    return _PreparedJobVolumes(
        volume_model_ids=[
            [volume_model.id for volume_model in mount_point] for mount_point in volume_models
        ],
        volumes=volumes,
    )


async def _load_assignment_candidate_fleets(
    context: _SubmittedJobContext,
) -> list[FleetModel]:
    async with get_session_ctx() as session:
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
    context: _SubmittedJobContext,
    fleet_id: uuid.UUID,
) -> Optional[FleetModel]:
    fleet_filters, instance_filters = await get_run_candidate_fleet_models_filters(
        session=session,
        project=context.project,
        run_model=context.run_model,
        run_spec=context.run.run_spec,
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
    context: _SubmittedJobContext,
    assignment: _ExistingInstanceAssignment,
    fleet_model: FleetModel,
) -> list[tuple[InstanceModel, InstanceOfferWithAvailability]]:
    return get_instance_offers_in_fleet(
        fleet_model=fleet_model,
        run_spec=context.run.run_spec,
        job=context.job,
        master_job_provisioning_data=assignment.master_job_provisioning_data,
        volumes=assignment.volumes,
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


async def _process_provisioning(context: _SubmittedJobContext) -> _ProvisioningResult:
    preconditions = await _process_preconditions(context=context)
    if not isinstance(preconditions, _ProcessedPreconditions):
        return preconditions

    if context.job_model.instance is not None:
        return await _process_existing_instance_provisioning(
            context=context,
            prepared_job_volumes=preconditions.prepared_job_volumes,
        )

    if context.run.run_spec.merged_profile.creation_policy == CreationPolicy.REUSE:
        logger.debug("%s: reuse instance failed", fmt(context.job_model))
        return _TerminateSubmittedJobResult(
            reason=JobTerminationReason.FAILED_TO_START_DUE_TO_NO_CAPACITY,
            message="Could not reuse any instances for this job",
        )

    return await _process_new_capacity_provisioning(
        context=context,
        preconditions=preconditions,
    )


async def _apply_provisioning_result(
    item: JobSubmittedPipelineItem,
    provisioning: _ProvisioningResult,
) -> None:
    async with get_session_ctx() as session:
        job_model = await _refetch_locked_job(session=session, item=item)
        if job_model is None:
            log_lock_token_changed_after_processing(logger, item)
            return

        if isinstance(provisioning, _DeferSubmittedJobResult):
            await _defer_submitted_job(
                session=session,
                job_model=job_model,
                log_message=provisioning.log_message,
            )
            return

        if isinstance(provisioning, _TerminateSubmittedJobResult):
            await _terminate_submitted_job(
                session=session,
                job_model=job_model,
                reason=provisioning.reason,
                message=provisioning.message,
            )
            return

        if isinstance(provisioning, _ExistingInstanceProvisioning):
            await _apply_existing_instance_provisioning(
                session=session,
                job_model=job_model,
                provisioning=provisioning,
            )
            return

        await _apply_new_capacity_provisioning(
            session=session,
            job_model=job_model,
            provisioning=provisioning,
        )


async def _process_existing_instance_provisioning(
    context: _SubmittedJobContext,
    prepared_job_volumes: _PreparedJobVolumes,
) -> _ExistingInstanceProvisioning:
    instance_model = get_or_error(context.job_model.instance)
    volume_attachment_result = await _process_volume_attachments(
        project=context.project,
        job_model=context.job_model,
        prepared_job_volumes=prepared_job_volumes,
        job_provisioning_data=get_or_error(get_instance_provisioning_data(instance_model)),
    )
    return _ExistingInstanceProvisioning(
        instance_id=instance_model.id,
        volume_attachment_result=volume_attachment_result,
    )


async def _apply_existing_instance_provisioning(
    session: AsyncSession,
    job_model: JobModel,
    provisioning: _ExistingInstanceProvisioning,
) -> None:
    context = await _load_submitted_job_context(session=session, job_model=job_model)
    res = await session.execute(
        select(InstanceModel)
        .where(InstanceModel.id == provisioning.instance_id)
        .execution_options(populate_existing=True)
    )
    instance_model = res.unique().scalar_one()
    context.job_model.job_provisioning_data = instance_model.job_provisioning_data
    if context.job_model.job_runtime_data is None:
        context.job_model.job_runtime_data = _prepare_job_runtime_data(
            offer=get_or_error(get_instance_offer(instance_model)),
            multinode=context.multinode,
        ).json()
    switch_job_status(session, context.job_model, JobStatus.PROVISIONING)
    await _apply_volume_attachment_result(
        session=session,
        job_model=context.job_model,
        instance_model=instance_model,
        volume_attachment_result=provisioning.volume_attachment_result,
    )
    _release_replica_jobs_from_master_wait(
        job_model=context.job_model,
        replica_job_models=_get_job_models_by_ids(
            job_models=context.run_model.jobs,
            job_model_ids=context.replica_job_model_ids,
        ),
        jobs_to_provision=context.jobs_to_provision,
    )
    await _mark_job_processed(session=session, job_model=context.job_model)


async def _process_new_capacity_provisioning(
    context: _SubmittedJobContext,
    preconditions: _ProcessedPreconditions,
) -> _ProvisioningResult:
    master_provisioning_data = (
        preconditions.master_job_provisioning_data
        or _get_fleet_master_provisioning_data(
            fleet_model=context.fleet_model,
            job=context.job,
        )
    )
    provision_new_capacity_result = await _provision_new_capacity(
        project=context.project,
        fleet_model=context.fleet_model,
        job_model=context.job_model,
        run=context.run,
        jobs=context.jobs_to_provision,
        project_ssh_public_key=context.project.ssh_public_key,
        project_ssh_private_key=context.project.ssh_private_key,
        master_job_provisioning_data=master_provisioning_data,
        volumes=preconditions.prepared_job_volumes.volumes,
    )
    if provision_new_capacity_result is None:
        logger.debug("%s: provisioning failed", fmt(context.job_model))
        return _TerminateSubmittedJobResult(
            reason=JobTerminationReason.FAILED_TO_START_DUE_TO_NO_CAPACITY,
        )

    created_fleet_model = None
    if context.fleet_model is None:
        created_fleet_model = await _create_fleet_model_for_job(
            project=context.project,
            run=context.run,
        )

    volume_attachment_result = None
    if isinstance(provision_new_capacity_result.provisioning_data, JobProvisioningData):
        volume_attachment_result = await _process_volume_attachments(
            project=context.project,
            job_model=context.job_model,
            prepared_job_volumes=preconditions.prepared_job_volumes,
            job_provisioning_data=provision_new_capacity_result.provisioning_data,
        )

    return _NewCapacityProvisioning(
        provisioning_data=provision_new_capacity_result.provisioning_data,
        offer=provision_new_capacity_result.offer,
        effective_profile=provision_new_capacity_result.effective_profile,
        created_fleet_model=created_fleet_model,
        new_placement_group_models=provision_new_capacity_result.new_placement_group_models,
        volume_attachment_result=volume_attachment_result,
    )


async def _apply_new_capacity_provisioning(
    session: AsyncSession,
    job_model: JobModel,
    provisioning: _NewCapacityProvisioning,
) -> None:
    fresh_context = await _load_submitted_job_context(session=session, job_model=job_model)
    fleet_model = fresh_context.fleet_model
    if provisioning.created_fleet_model is not None:
        fleet_model = provisioning.created_fleet_model
        session.add(fleet_model)
        fresh_context.job_model.fleet = fleet_model
        events.emit(
            session,
            f"Fleet created for job. Fleet status: {fleet_model.status.upper()}",
            actor=events.SystemActor(),
            targets=[
                events.Target.from_model(fleet_model),
                events.Target.from_model(fresh_context.job_model),
            ],
        )

    assert fleet_model is not None
    for placement_group_model in provisioning.new_placement_group_models:
        session.add(placement_group_model)

    instance_models, _ = await _materialize_newly_provisioned_capacity(
        session=session,
        context=fresh_context,
        fleet_model=fleet_model,
        provisioning_data=provisioning.provisioning_data,
        offer=provisioning.offer,
        effective_profile=provisioning.effective_profile,
    )
    if provisioning.volume_attachment_result is not None:
        assert len(instance_models) == 1
        await _apply_volume_attachment_result(
            session=session,
            job_model=fresh_context.job_model,
            instance_model=instance_models[0],
            volume_attachment_result=provisioning.volume_attachment_result,
        )
    _release_replica_jobs_from_master_wait(
        job_model=fresh_context.job_model,
        replica_job_models=_get_job_models_by_ids(
            job_models=fresh_context.run_model.jobs,
            job_model_ids=fresh_context.replica_job_model_ids,
        ),
        jobs_to_provision=fresh_context.jobs_to_provision,
    )
    await _mark_job_processed(session=session, job_model=fresh_context.job_model)


async def _materialize_newly_provisioned_capacity(
    session: AsyncSession,
    context: _SubmittedJobContext,
    fleet_model: FleetModel,
    provisioning_data: Union[JobProvisioningData, ComputeGroupProvisioningData],
    offer: InstanceOfferWithAvailability,
    effective_profile: Profile,
) -> tuple[list[InstanceModel], Optional[ComputeGroupModel]]:
    (
        provisioned_jobs,
        job_provisioning_datas,
        compute_group_model,
    ) = _resolve_provisioned_jobs_and_data(
        context=context,
        fleet_model=fleet_model,
        provisioning_data=provisioning_data,
    )
    if compute_group_model is not None:
        session.add(compute_group_model)

    instance_models = await _create_instance_models_for_provisioned_jobs(
        session=session,
        context=context,
        fleet_model=fleet_model,
        compute_group_model=compute_group_model,
        provisioned_jobs=provisioned_jobs,
        job_provisioning_datas=job_provisioning_datas,
        offer=offer,
        effective_profile=effective_profile,
    )

    logger.info(
        "%s: provisioned %s new instance(s)",
        fmt(context.job_model),
        len(provisioned_jobs),
    )
    return instance_models, compute_group_model


def _resolve_provisioned_jobs_and_data(
    context: _SubmittedJobContext,
    fleet_model: FleetModel,
    provisioning_data: Union[JobProvisioningData, ComputeGroupProvisioningData],
) -> tuple[list[Job], list[JobProvisioningData], Optional[ComputeGroupModel]]:
    if isinstance(provisioning_data, ComputeGroupProvisioningData):
        compute_group_model = ComputeGroupModel(
            id=uuid.uuid4(),
            project=context.project,
            fleet=fleet_model,
            status=ComputeGroupStatus.RUNNING,
            provisioning_data=provisioning_data.json(),
        )
        return (
            context.jobs_to_provision,
            provisioning_data.job_provisioning_datas,
            compute_group_model,
        )
    return [context.job], [provisioning_data], None


async def _create_instance_models_for_provisioned_jobs(
    session: AsyncSession,
    context: _SubmittedJobContext,
    fleet_model: FleetModel,
    compute_group_model: Optional[ComputeGroupModel],
    provisioned_jobs: list[Job],
    job_provisioning_datas: list[JobProvisioningData],
    offer: InstanceOfferWithAvailability,
    effective_profile: Profile,
) -> list[InstanceModel]:
    provisioned_job_models = _get_job_models_for_jobs(context.run_model.jobs, provisioned_jobs)
    instance_models: list[InstanceModel] = []
    taken_instance_nums = await _get_taken_instance_nums(session, fleet_model)
    for provisioned_job_model, job_provisioning_data in zip(
        provisioned_job_models, job_provisioning_datas
    ):
        provisioned_job_model.fleet_id = fleet_model.id
        provisioned_job_model.job_provisioning_data = job_provisioning_data.json()
        switch_job_status(session, provisioned_job_model, JobStatus.PROVISIONING)
        instance_num = get_next_instance_num(taken_instance_nums)
        instance_model = _create_instance_model_for_job(
            project=context.project,
            fleet_model=fleet_model,
            compute_group_model=compute_group_model,
            job_model=provisioned_job_model,
            job_provisioning_data=job_provisioning_data,
            offer=offer,
            instance_num=instance_num,
            profile=effective_profile,
        )
        instance_models.append(instance_model)
        taken_instance_nums.add(instance_num)
        provisioned_job_model.job_runtime_data = _prepare_job_runtime_data(
            offer, context.multinode
        ).json()
        session.add(instance_model)
        events.emit(
            session,
            f"Instance created for job. Instance status: {instance_model.status.upper()}",
            actor=events.SystemActor(),
            targets=[
                events.Target.from_model(instance_model),
                events.Target.from_model(provisioned_job_model),
            ],
        )
        provisioned_job_model.used_instance_id = instance_model.id
        provisioned_job_model.last_processed_at = get_current_datetime()
    return instance_models


async def _get_taken_instance_nums(session: AsyncSession, fleet_model: FleetModel) -> set[int]:
    res = await session.execute(
        select(InstanceModel.instance_num).where(
            InstanceModel.fleet_id == fleet_model.id,
            InstanceModel.deleted.is_(False),
        )
    )
    return set(res.scalars().all())


def _create_instance_model_for_job(
    project: ProjectModel,
    fleet_model: FleetModel,
    compute_group_model: Optional[ComputeGroupModel],
    job_model: JobModel,
    job_provisioning_data: JobProvisioningData,
    offer: InstanceOfferWithAvailability,
    instance_num: int,
    profile: Profile,
) -> InstanceModel:
    if not job_provisioning_data.dockerized:
        termination_policy = TerminationPolicy.DESTROY_AFTER_IDLE
        termination_idle_time = 0
    else:
        termination_policy, termination_idle_time = get_termination(
            profile, DEFAULT_RUN_TERMINATION_IDLE_TIME
        )
    return InstanceModel(
        id=uuid.uuid4(),
        name=f"{fleet_model.name}-{instance_num}",
        instance_num=instance_num,
        project=project,
        fleet=fleet_model,
        compute_group=compute_group_model,
        created_at=get_current_datetime(),
        started_at=get_current_datetime(),
        status=InstanceStatus.PROVISIONING,
        unreachable=False,
        job_provisioning_data=job_provisioning_data.json(),
        offer=offer.json(),
        termination_policy=termination_policy,
        termination_idle_time=termination_idle_time,
        jobs=[job_model],
        backend=offer.backend,
        price=offer.price,
        region=offer.region,
        volume_attachments=[],
        total_blocks=1,
        busy_blocks=1,
    )


async def _process_volume_attachments(
    project: ProjectModel,
    job_model: JobModel,
    prepared_job_volumes: _PreparedJobVolumes,
    job_provisioning_data: JobProvisioningData,
) -> _VolumeAttachmentResult:
    if len(prepared_job_volumes.volume_model_ids) == 0:
        return _VolumeAttachmentResult(attachments=[])

    volume_models = await _load_volume_models(
        volume_model_ids=prepared_job_volumes.volume_model_ids
    )
    backend = await get_project_backend_by_type_or_error(
        project=project,
        backend_type=job_provisioning_data.backend,
    )
    compute = backend.compute()
    assert isinstance(compute, ComputeWithVolumeSupport)

    attachments: list[_VolumeAttachmentPayload] = []
    for mount_point_volume_models in volume_models:
        for volume_model in mount_point_volume_models:
            volume = volume_model_to_volume(volume_model)
            try:
                if volume_model.deleted:
                    raise ServerClientError("Cannot attach a deleted volume")
                if volume_model.to_be_deleted:
                    raise ServerClientError("Cannot attach a volume marked for deletion")
                if volume_model.lock_expires_at is not None:
                    raise ServerClientError("Cannot attach a volume locked for processing")
                if (
                    job_provisioning_data.get_base_backend() != volume.configuration.backend
                    or job_provisioning_data.region.lower() != volume.configuration.region.lower()
                ):
                    continue
                if volume.provisioning_data is None or not volume.provisioning_data.attachable:
                    continue
                attachment_data = await run_async(
                    compute.attach_volume,
                    volume=volume,
                    provisioning_data=job_provisioning_data,
                )
                attachments.append(
                    _VolumeAttachmentPayload(
                        volume_id=volume_model.id,
                        attachment_data=attachment_data.json(),
                        volume_name=volume.name,
                    )
                )
                break
            except ServerClientError as e:
                logger.info("%s: failed to attach volume: %s", fmt(job_model), repr(e))
                return _VolumeAttachmentResult(
                    attachments=attachments,
                    termination_message=f"Failed to attach volume: {e.msg}",
                )
            except BackendError as e:
                logger.warning("%s: failed to attach volume: %s", fmt(job_model), repr(e))
                return _VolumeAttachmentResult(
                    attachments=attachments,
                    termination_message=f"Failed to attach volume: {str(e)}",
                )
            except Exception:
                logger.exception("%s: got exception when attaching volume", fmt(job_model))
                return _VolumeAttachmentResult(
                    attachments=attachments,
                    termination_message="Failed to attach volume: unexpected error",
                )
    return _VolumeAttachmentResult(attachments=attachments)


async def _load_volume_models(
    volume_model_ids: list[list[uuid.UUID]],
) -> list[list[VolumeModel]]:
    volume_ids = sorted(
        volume_id
        for mount_point_volume_ids in volume_model_ids
        for volume_id in mount_point_volume_ids
    )
    async with get_session_ctx() as session:
        res = await session.execute(
            select(VolumeModel)
            .where(VolumeModel.id.in_(volume_ids))
            .options(joinedload(VolumeModel.user).load_only(UserModel.name))
        )
        loaded_volume_models = list(res.unique().scalars().all())
    volume_models_by_id = {volume_model.id: volume_model for volume_model in loaded_volume_models}
    return [
        [volume_models_by_id[volume_id] for volume_id in mount_point_volume_ids]
        for mount_point_volume_ids in volume_model_ids
    ]


async def _apply_volume_attachment_result(
    session: AsyncSession,
    job_model: JobModel,
    instance_model: InstanceModel,
    volume_attachment_result: _VolumeAttachmentResult,
) -> None:
    job_runtime_data = get_or_error(get_job_runtime_data(job_model))
    job_runtime_data.volume_names = [
        attachment.volume_name for attachment in volume_attachment_result.attachments
    ]
    job_model.job_runtime_data = job_runtime_data.json()

    volume_ids = [attachment.volume_id for attachment in volume_attachment_result.attachments]
    if volume_ids:
        now = get_current_datetime()
        await session.execute(
            update(VolumeModel)
            .where(VolumeModel.id.in_(volume_ids))
            .values(last_job_processed_at=now)
        )
        for attachment in volume_attachment_result.attachments:
            session.add(
                VolumeAttachmentModel(
                    volume_id=attachment.volume_id,
                    instance=instance_model,
                    attachment_data=attachment.attachment_data,
                )
            )

    if volume_attachment_result.termination_message is None:
        return

    job_model.termination_reason = JobTerminationReason.VOLUME_ERROR
    job_model.termination_reason_message = volume_attachment_result.termination_message
    switch_job_status(session, job_model, JobStatus.TERMINATING)


def _get_cluster_fleet_spec(fleet_model: FleetModel) -> Optional[FleetSpec]:
    fleet_spec = get_fleet_spec(fleet_model)
    if fleet_spec.configuration.placement != InstanceGroupPlacement.CLUSTER:
        return None
    return fleet_spec


def _get_fleet_master_provisioning_data(
    fleet_model: Optional[FleetModel],
    job: Job,
) -> Optional[JobProvisioningData]:
    if not is_master_job(job) or fleet_model is None:
        return None

    fleet_spec = _get_cluster_fleet_spec(fleet_model)
    if fleet_spec is None:
        return None

    return get_fleet_master_instance_provisioning_data(
        fleet_model=fleet_model,
        fleet_spec=fleet_spec,
    )


def _select_jobs_to_provision(job: Job, replica_jobs: list[Job], job_model: JobModel) -> list[Job]:
    jobs_to_provision = [job]
    if is_multinode_job(job) and is_master_job(job) and job_model.waiting_master_job is not None:
        jobs_to_provision = replica_jobs
    return jobs_to_provision


def _release_replica_jobs_from_master_wait(
    job_model: JobModel,
    replica_job_models: list[JobModel],
    jobs_to_provision: list[Job],
) -> None:
    if len(jobs_to_provision) > 1:
        logger.debug("%s: allow replica jobs to be provisioned one-by-one", fmt(job_model))
        for replica_job_model in replica_job_models:
            replica_job_model.waiting_master_job = False


async def _provision_new_capacity(
    project: ProjectModel,
    job_model: JobModel,
    run: Run,
    jobs: list[Job],
    project_ssh_public_key: str,
    project_ssh_private_key: str,
    master_job_provisioning_data: Optional[JobProvisioningData] = None,
    volumes: Optional[list[list[Volume]]] = None,
    fleet_model: Optional[FleetModel] = None,
) -> Optional[_ProvisionNewCapacityResult]:
    job = jobs[0]
    if volumes is None:
        volumes = []
    effective_profile_and_requirements = _get_effective_profile_and_requirements(
        job_model=job_model,
        run=run,
        job=job,
        fleet_model=fleet_model,
    )
    if effective_profile_and_requirements is None:
        return None
    profile, requirements = effective_profile_and_requirements

    placement_group_models = await _load_fleet_placement_group_models(
        fleet_id=fleet_model.id if fleet_model else None,
    )
    new_placement_group_models: list[PlacementGroupModel] = []
    placement_group_model = get_placement_group_model_for_job(
        placement_group_models=placement_group_models,
        fleet_model=fleet_model,
    )
    multinode = requirements.multinode or is_multinode_job(job)
    offers = await get_offers_by_requirements(
        project=project,
        profile=profile,
        requirements=requirements,
        exclude_not_available=True,
        multinode=multinode,
        master_job_provisioning_data=master_job_provisioning_data,
        volumes=volumes,
        privileged=job.job_spec.privileged,
        instance_mounts=check_run_spec_requires_instance_mounts(run.run_spec),
        placement_group=placement_group_model_to_placement_group_optional(placement_group_model),
    )
    for backend, offer in offers[: settings.MAX_OFFERS_TRIED]:
        logger.debug(
            "%s: trying %s in %s/%s for $%0.4f per hour",
            fmt(job_model),
            offer.instance.name,
            offer.backend.value,
            offer.region,
            offer.price,
        )
        offer_volumes = _get_offer_volumes(volumes, offer)
        job_configurations = [
            JobConfiguration(job=job_to_run, volumes=offer_volumes) for job_to_run in jobs
        ]
        compute = backend.compute()
        if master_job_provisioning_data is not None:
            offer = get_instance_offer_with_restricted_az(
                instance_offer=offer,
                master_job_provisioning_data=master_job_provisioning_data,
            )
        if (
            fleet_model is not None
            and len(fleet_model.instances) == 0
            and is_cloud_cluster(fleet_model)
            and offer.backend in BACKENDS_WITH_PLACEMENT_GROUPS_SUPPORT
            and isinstance(compute, ComputeWithPlacementGroupSupport)
            and (
                compute.are_placement_groups_compatible_with_reservations(offer.backend)
                or job.job_spec.requirements.reservation is None
            )
        ):
            placement_group_model = await find_or_create_suitable_placement_group(
                fleet_model=fleet_model,
                placement_groups=placement_group_models,
                instance_offer=offer,
                compute=compute,
            )
            if placement_group_model is None:
                continue
            if placement_group_model.id not in {pg.id for pg in placement_group_models}:
                new_placement_group_models.append(placement_group_model)
                placement_group_models.append(placement_group_model)
        try:
            if len(jobs) > 1 and offer.backend in BACKENDS_WITH_GROUP_PROVISIONING_SUPPORT:
                assert isinstance(compute, ComputeWithGroupProvisioningSupport)
                compute_group_provisioning_data = await run_async(
                    compute.run_jobs,
                    run,
                    job_configurations,
                    offer,
                    project_ssh_public_key,
                    project_ssh_private_key,
                    placement_group_model_to_placement_group_optional(placement_group_model),
                )
                return _ProvisionNewCapacityResult(
                    provisioning_data=compute_group_provisioning_data,
                    offer=offer,
                    effective_profile=profile,
                    new_placement_group_models=new_placement_group_models,
                )
            job_provisioning_data = await run_async(
                compute.run_job,
                run,
                job,
                offer,
                project_ssh_public_key,
                project_ssh_private_key,
                offer_volumes,
                placement_group_model_to_placement_group_optional(placement_group_model),
            )
            return _ProvisionNewCapacityResult(
                provisioning_data=job_provisioning_data,
                offer=offer,
                effective_profile=profile,
                new_placement_group_models=new_placement_group_models,
            )
        except BackendError as e:
            logger.warning(
                "%s: %s launch in %s/%s failed: %s",
                fmt(job_model),
                offer.instance.name,
                offer.backend.value,
                offer.region,
                repr(e),
            )
            continue
        except Exception:
            logger.exception(
                "%s: got exception when launching %s in %s/%s",
                fmt(job_model),
                offer.instance.name,
                offer.backend.value,
                offer.region,
            )
            continue
        finally:
            if fleet_model is not None and len(fleet_model.instances) == 0:
                for placement_group in placement_group_models:
                    if (
                        placement_group_model is None
                        or placement_group.id != placement_group_model.id
                    ):
                        placement_group.fleet_deleted = True
    return None


async def _load_fleet_placement_group_models(
    fleet_id: Optional[uuid.UUID],
) -> list["PlacementGroupModel"]:
    async with get_session_ctx() as session:
        return await get_fleet_placement_group_models(
            session=session,
            fleet_id=fleet_id,
        )


def _get_effective_profile_and_requirements(
    job_model: JobModel,
    run: Run,
    job: Job,
    fleet_model: Optional[FleetModel],
) -> Optional[tuple[Profile, Requirements]]:
    effective_profile = run.run_spec.merged_profile
    requirements = job.job_spec.requirements
    if fleet_model is None:
        return effective_profile, requirements

    fleet_spec = get_fleet_spec(fleet_model)
    try:
        check_can_create_new_cloud_instance_in_fleet(fleet_model, fleet_spec)
        effective_profile, requirements = get_run_profile_and_requirements_in_fleet(
            job=job,
            run_spec=run.run_spec,
            fleet_spec=fleet_spec,
        )
    except ValueError as e:
        logger.debug("%s: %s", fmt(job_model), e.args[0])
        return None
    return effective_profile, requirements


async def _create_fleet_model_for_job(
    project: ProjectModel,
    run: Run,
) -> FleetModel:
    placement = InstanceGroupPlacement.ANY
    if run.run_spec.configuration.type == "task" and run.run_spec.configuration.nodes > 1:
        placement = InstanceGroupPlacement.CLUSTER
    nodes = get_nodes_required_num(run.run_spec)
    lock_namespace = f"fleet_names_{project.name}"
    async with get_session_ctx() as session:
        if is_db_sqlite():
            await session.commit()
        elif is_db_postgres():
            await session.execute(
                select(func.pg_advisory_xact_lock(string_to_lock_id(lock_namespace)))
            )
        async with get_locker(get_db().dialect_name).get_lockset(lock_namespace)[0]:
            fleet_name = await generate_fleet_name(session=session, project=project)
    spec = FleetSpec(
        configuration=FleetConfiguration(
            name=fleet_name,
            placement=placement,
            reservation=run.run_spec.configuration.reservation,
            nodes=FleetNodesSpec(
                min=nodes,
                target=nodes,
                max=None,
            ),
        ),
        profile=run.run_spec.merged_profile,
        autocreated=True,
    )
    return FleetModel(
        id=uuid.uuid4(),
        name=fleet_name,
        project=project,
        status=FleetStatus.ACTIVE,
        spec=spec.json(),
        instances=[],
    )


def _get_offer_volumes(
    volumes: list[list[Volume]],
    offer: InstanceOfferWithAvailability,
) -> list[Volume]:
    return [
        _get_offer_mount_point_volume(mount_point_volumes, offer)
        for mount_point_volumes in volumes
    ]


def _get_offer_mount_point_volume(
    volumes: list[Volume],
    offer: InstanceOfferWithAvailability,
) -> Volume:
    for volume in volumes:
        if (
            volume.configuration.backend != offer.backend
            or volume.configuration.region.lower() != offer.region.lower()
        ):
            continue
        return volume
    raise ServerClientError("Failed to find an eligible volume for the mount point")


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
