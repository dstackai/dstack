import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Iterable, Optional, Sequence

import sentry_sdk
from sqlalchemy import ColumnElement, and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, load_only

from dstack._internal.core.backends.base.compute import ComputeWithResourceListingSupport
from dstack._internal.core.backends.features import get_backends_with_resource_listing_support
from dstack._internal.core.errors import BackendError, NotYetTerminated
from dstack._internal.core.models.backends.orphans import (
    ListedResourceGroup,
    OrphanCleanupMode,
    OwnerType,
)
from dstack._internal.core.models.instances import InstanceStatus
from dstack._internal.core.models.runs import JobStatus
from dstack._internal.server import settings
from dstack._internal.server.background.pipeline_tasks.base import (
    Fetcher,
    Heartbeater,
    ItemUpdateMap,
    Pipeline,
    PipelineItem,
    UpdateMapDateTime,
    Worker,
    log_lock_token_changed_after_processing,
    log_lock_token_mismatch,
    resolve_now_placeholders,
    set_processed_update_map_fields,
    set_unlock_update_map_fields,
)
from dstack._internal.server.db import get_db, get_session_ctx
from dstack._internal.server.models import (
    BackendModel,
    InstanceModel,
    JobModel,
    OrphanCleanupModel,
    ProjectModel,
)
from dstack._internal.server.services import backends as backends_services
from dstack._internal.server.services import events
from dstack._internal.server.services.instances import get_instance_provisioning_data
from dstack._internal.server.services.locking import get_locker
from dstack._internal.server.services.pipelines import PipelineHinterProtocol
from dstack._internal.server.utils import tracing
from dstack._internal.utils.common import batched, get_current_datetime, get_or_error, run_async
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


class OrphanCleanupPipeline(Pipeline[PipelineItem]):
    def __init__(
        self,
        workers_num: int = 5,
        queue_lower_limit_factor: float = 0.5,
        queue_upper_limit_factor: float = 2.0,
        min_processing_interval: Optional[timedelta] = None,
        lock_timeout: timedelta = timedelta(seconds=60),
        heartbeat_trigger: timedelta = timedelta(seconds=20),
        *,
        pipeline_hinter: PipelineHinterProtocol,
    ) -> None:
        if min_processing_interval is None:
            if settings.ORPHAN_CLEANUP_INTERVAL_SECONDS <= 0:
                raise ValueError("DSTACK_SERVER_ORPHAN_CLEANUP_INTERVAL_SECONDS must be positive")
            min_processing_interval = timedelta(seconds=settings.ORPHAN_CLEANUP_INTERVAL_SECONDS)
        super().__init__(
            workers_num=workers_num,
            queue_lower_limit_factor=queue_lower_limit_factor,
            queue_upper_limit_factor=queue_upper_limit_factor,
            min_processing_interval=min_processing_interval,
            lock_timeout=lock_timeout,
            heartbeat_trigger=heartbeat_trigger,
        )
        self.__heartbeater = Heartbeater[PipelineItem](
            model_type=OrphanCleanupModel,
            lock_timeout=self._lock_timeout,
            heartbeat_trigger=self._heartbeat_trigger,
        )
        self.__fetcher = OrphanCleanupFetcher(
            queue=self._queue,
            queue_desired_minsize=self._queue_desired_minsize,
            min_processing_interval=self._min_processing_interval,
            lock_timeout=self._lock_timeout,
            heartbeater=self._heartbeater,
        )
        self.__workers = [
            OrphanCleanupWorker(
                queue=self._queue,
                heartbeater=self._heartbeater,
                pipeline_hinter=pipeline_hinter,
            )
            for _ in range(self._workers_num)
        ]

    @property
    def hint_fetch_model_name(self) -> str:
        return OrphanCleanupModel.__name__

    @property
    def _heartbeater(self) -> Heartbeater[PipelineItem]:
        return self.__heartbeater

    @property
    def _fetcher(self) -> Fetcher[PipelineItem]:
        return self.__fetcher

    @property
    def _workers(self) -> Sequence["OrphanCleanupWorker"]:
        return self.__workers


class OrphanCleanupFetcher(Fetcher[PipelineItem]):
    def __init__(
        self,
        queue: asyncio.Queue[PipelineItem],
        queue_desired_minsize: int,
        min_processing_interval: timedelta,
        lock_timeout: timedelta,
        heartbeater: Heartbeater[PipelineItem],
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

    @tracing.instrument_pipeline_task("OrphanCleanupFetcher.fetch")
    async def fetch(self, limit: int) -> list[PipelineItem]:
        orphan_cleanup_lock, _ = get_locker(get_db().dialect_name).get_lockset(
            OrphanCleanupModel.__tablename__
        )
        async with orphan_cleanup_lock:
            async with get_session_ctx() as session:
                now = get_current_datetime()
                res = await session.execute(
                    select(OrphanCleanupModel)
                    .join(BackendModel, BackendModel.id == OrphanCleanupModel.backend_id)
                    .join(ProjectModel, ProjectModel.id == BackendModel.project_id)
                    .where(
                        ProjectModel.deleted == False,
                        BackendModel.type.in_(get_backends_with_resource_listing_support()),
                        _eligibility_filter(),
                        _retry_delay_filter(now),
                        or_(
                            OrphanCleanupModel.last_processed_at
                            <= now - self._min_processing_interval,
                            OrphanCleanupModel.last_processed_at == OrphanCleanupModel.created_at,
                        ),
                        or_(
                            OrphanCleanupModel.lock_expires_at.is_(None),
                            OrphanCleanupModel.lock_expires_at < now,
                        ),
                        or_(
                            OrphanCleanupModel.lock_owner.is_(None),
                            OrphanCleanupModel.lock_owner == OrphanCleanupPipeline.__name__,
                        ),
                    )
                    .order_by(OrphanCleanupModel.last_processed_at.asc())
                    .limit(limit)
                    .with_for_update(skip_locked=True, key_share=True, of=OrphanCleanupModel)
                    .options(
                        load_only(
                            OrphanCleanupModel.id,
                            OrphanCleanupModel.lock_token,
                            OrphanCleanupModel.lock_expires_at,
                        )
                    )
                )
                orphan_cleanup_models = list(res.scalars().all())
                lock_expires_at = get_current_datetime() + self._lock_timeout
                lock_token = uuid.uuid4()
                items = []
                for orphan_cleanup_model in orphan_cleanup_models:
                    prev_lock_expired = orphan_cleanup_model.lock_expires_at is not None
                    orphan_cleanup_model.lock_expires_at = lock_expires_at
                    orphan_cleanup_model.lock_token = lock_token
                    orphan_cleanup_model.lock_owner = OrphanCleanupPipeline.__name__
                    items.append(
                        PipelineItem(
                            __tablename__=OrphanCleanupModel.__tablename__,
                            id=orphan_cleanup_model.id,
                            lock_expires_at=lock_expires_at,
                            lock_token=lock_token,
                            prev_lock_expired=prev_lock_expired,
                        )
                    )
                await session.commit()
        return items


class OrphanCleanupWorker(Worker[PipelineItem]):
    def __init__(
        self,
        queue: asyncio.Queue[PipelineItem],
        heartbeater: Heartbeater[PipelineItem],
        pipeline_hinter: PipelineHinterProtocol,
    ) -> None:
        super().__init__(
            queue=queue,
            heartbeater=heartbeater,
            pipeline_hinter=pipeline_hinter,
        )

    @tracing.instrument_pipeline_task("OrphanCleanupWorker.process")
    async def process(self, item: PipelineItem):
        process_context = await _load_process_context(item)
        if process_context is None:
            return
        result = await _process_orphan_cleanup(process_context)
        await _apply_process_result(item, process_context, result)


@dataclass
class _ProcessContext:
    orphan_cleanup_model: OrphanCleanupModel


class _OrphanCleanupUpdateMap(ItemUpdateMap, total=False):
    cleanup_attempt: int
    clean_at: UpdateMapDateTime
    clean_mode: OrphanCleanupMode


@dataclass
class _OrphanEvent:
    message: str
    target: events.Target


@dataclass
class _ProcessResult:
    update_map: _OrphanCleanupUpdateMap
    orphan_events: list[_OrphanEvent] = field(default_factory=list)


class _ResourceGroupDecision(str, Enum):
    IGNORE = "ignore"
    SKIP = "skip"
    ORPHAN = "orphan"
    TRACKED = "tracked"


def _eligibility_filter() -> ColumnElement[bool]:
    has_new_instance_activity = (
        select(InstanceModel.id)
        .where(
            InstanceModel.project_id == BackendModel.project_id,
            InstanceModel.provider_ref.is_not(None),
            or_(
                InstanceModel.created_at >= OrphanCleanupModel.clean_at,
                InstanceModel.started_at >= OrphanCleanupModel.clean_at,
                InstanceModel.finished_at >= OrphanCleanupModel.clean_at,
            ),
        )
        .exists()
    )
    # If `run_job()` fails after creating provider resources, the job is terminated and its
    # placeholder instance is deleted, so only the job's activity indicates possible orphans.
    # Finished jobs are no longer processed, so `last_processed_at` is the finish time.
    has_new_job_activity = (
        select(JobModel.id)
        .where(
            JobModel.project_id == BackendModel.project_id,
            JobModel.provider_ref.is_not(None),
            JobModel.status.in_(JobStatus.finished_statuses()),
            JobModel.last_processed_at >= OrphanCleanupModel.clean_at,
        )
        .exists()
    )
    return or_(
        OrphanCleanupModel.clean_at.is_(None),
        OrphanCleanupModel.clean_mode != settings.ORPHAN_CLEANUP_MODE,
        has_new_instance_activity,
        has_new_job_activity,
    )


_CLEANUP_RETRY_INTERVAL_MULTIPLIERS = [2, 6, 24]
"""Retry delays after failed or unclean cleanups, as multiples of the cleanup interval."""


def _retry_delay_filter(now: datetime) -> ColumnElement[bool]:
    """
    SQL-portable way to filter by retry delay depending on `cleanup_attempt`.
    """
    interval = timedelta(seconds=settings.ORPHAN_CLEANUP_INTERVAL_SECONDS)
    filters = [
        and_(
            OrphanCleanupModel.cleanup_attempt == i,
            OrphanCleanupModel.last_processed_at < now - interval * multiplier,
        )
        for i, multiplier in enumerate(_CLEANUP_RETRY_INTERVAL_MULTIPLIERS[:-1], start=1)
    ]
    filters.append(
        and_(
            OrphanCleanupModel.cleanup_attempt >= len(_CLEANUP_RETRY_INTERVAL_MULTIPLIERS),
            OrphanCleanupModel.last_processed_at
            < now - interval * _CLEANUP_RETRY_INTERVAL_MULTIPLIERS[-1],
        )
    )
    return or_(OrphanCleanupModel.cleanup_attempt == 0, *filters)


async def _load_process_context(item: PipelineItem) -> Optional[_ProcessContext]:
    async with get_session_ctx() as session:
        res = await session.execute(
            select(OrphanCleanupModel)
            .where(
                OrphanCleanupModel.id == item.id,
                OrphanCleanupModel.lock_token == item.lock_token,
            )
            .options(
                joinedload(OrphanCleanupModel.backend)
                .joinedload(BackendModel.project)
                .joinedload(ProjectModel.backends)
            )
        )
        orphan_cleanup_model = res.unique().scalar_one_or_none()
    if orphan_cleanup_model is None:
        log_lock_token_mismatch(logger, item)
        return
    return _ProcessContext(orphan_cleanup_model=orphan_cleanup_model)


async def _process_orphan_cleanup(process_context: _ProcessContext) -> _ProcessResult:
    orphan_cleanup_model = process_context.orphan_cleanup_model
    backend = await backends_services.get_project_backend_by_type(
        project=orphan_cleanup_model.backend.project,
        backend_type=orphan_cleanup_model.backend.type,
    )
    if backend is None:
        logger.warning(
            "Failed to clean up orphaned resources in %s/%s: backend is not available",
            orphan_cleanup_model.backend.project.name,
            orphan_cleanup_model.backend.type.value,
        )
        return _get_failed_cleanup_process_result(orphan_cleanup_model)
    compute = backend.compute()
    assert isinstance(compute, ComputeWithResourceListingSupport)
    listed_at = get_current_datetime()
    try:
        resource_listing = await run_async(compute.list_resource_groups)
    except BackendError as e:
        logger.warning(
            "Failed to list resource groups in %s/%s due to backend error: %s",
            orphan_cleanup_model.backend.project.name,
            orphan_cleanup_model.backend.type.value,
            repr(e),
        )
        return _get_failed_cleanup_process_result(orphan_cleanup_model)
    except Exception:
        logger.exception(
            "Failed to list resource groups in %s/%s due to unexpected error",
            orphan_cleanup_model.backend.project.name,
            orphan_cleanup_model.backend.type.value,
        )
        return _get_failed_cleanup_process_result(orphan_cleanup_model)
    for failure in resource_listing.failures:
        logger.warning(
            "Failed to list resources of %s in %s for orphan cleanup in %s/%s: %s",
            failure.backend.value,
            failure.region if failure.region is not None else "all regions",
            orphan_cleanup_model.backend.project.name,
            orphan_cleanup_model.backend.type.value,
            failure.message,
        )
    resource_groups = resource_listing.resource_groups
    owner_records = await _load_owner_records(
        project_id=orphan_cleanup_model.backend.project_id,
        resource_groups=resource_groups,
    )
    decisions = [
        _get_resource_group_decision(
            orphan_cleanup_model, resource_group, owner_records, listed_at
        )
        for resource_group in resource_groups
    ]
    final_decisions: list[_ResourceGroupDecision] = []
    orphan_events: list[_OrphanEvent] = []
    for resource_group, decision in zip(resource_groups, decisions):
        if decision == _ResourceGroupDecision.ORPHAN:
            decision = await _handle_orphaned_resource_group(
                compute, orphan_cleanup_model, resource_group
            )
            if decision == _ResourceGroupDecision.ORPHAN:
                orphan_events.append(_get_orphan_event(resource_group, owner_records))
        final_decisions.append(decision)
    if any(d is _ResourceGroupDecision.SKIP for d in final_decisions):
        result = _get_skips_cleanup_process_result(orphan_cleanup_model)
    elif len(resource_listing.failures) > 0:
        result = _get_partial_cleanup_process_result()
    else:
        result = _get_success_cleanup_process_result(listed_at)
    result.orphan_events = orphan_events
    return result


_PROVIDER_REF_BATCH_SIZE = 100


@dataclass
class _OwnerRecords:
    instances: dict[str, InstanceModel]
    jobs: dict[str, JobModel]
    """Jobs whose `provider_ref` is not found among instances. A job's instance inherits
    the job's `provider_ref` on successful provisioning, so a job matches only resources
    left by failed provisioning. See `JobModel.provider_ref`."""


async def _load_owner_records(
    project_id: uuid.UUID, resource_groups: list[ListedResourceGroup]
) -> _OwnerRecords:
    instance_refs = {
        resource_group.provider_ref
        for resource_group in resource_groups
        if resource_group.owner_type == OwnerType.INSTANCE
    }
    async with get_session_ctx() as session:
        instances = await _load_instances_by_provider_ref(session, project_id, instance_refs)
        jobs = await _load_jobs_by_provider_ref(
            session, project_id, instance_refs - instances.keys()
        )
    return _OwnerRecords(instances=instances, jobs=jobs)


async def _load_instances_by_provider_ref(
    session: AsyncSession, project_id: uuid.UUID, provider_refs: Iterable[str]
) -> dict[str, InstanceModel]:
    # Soft-deleted instances are included since termination sets `deleted`.
    instances: dict[str, InstanceModel] = {}
    for batch in batched(provider_refs, _PROVIDER_REF_BATCH_SIZE):
        res = await session.execute(
            select(InstanceModel)
            .where(
                InstanceModel.project_id == project_id,
                InstanceModel.provider_ref.in_(batch),
            )
            .options(
                load_only(
                    InstanceModel.id,
                    InstanceModel.project_id,
                    InstanceModel.fleet_id,
                    InstanceModel.name,
                    InstanceModel.provider_ref,
                    InstanceModel.status,
                    InstanceModel.job_provisioning_data,
                )
            )
        )
        for instance_model in res.scalars().all():
            instances[get_or_error(instance_model.provider_ref)] = instance_model
    return instances


async def _load_jobs_by_provider_ref(
    session: AsyncSession, project_id: uuid.UUID, provider_refs: Iterable[str]
) -> dict[str, JobModel]:
    jobs: dict[str, JobModel] = {}
    for batch in batched(provider_refs, _PROVIDER_REF_BATCH_SIZE):
        res = await session.execute(
            select(JobModel)
            .where(
                JobModel.project_id == project_id,
                JobModel.provider_ref.in_(batch),
            )
            .options(
                load_only(
                    JobModel.id,
                    JobModel.project_id,
                    JobModel.run_id,
                    JobModel.job_name,
                    JobModel.provider_ref,
                    JobModel.status,
                )
            )
        )
        for job_model in res.scalars().all():
            jobs[get_or_error(job_model.provider_ref)] = job_model
    return jobs


def _get_resource_group_decision(
    orphan_cleanup_model: OrphanCleanupModel,
    resource_group: ListedResourceGroup,
    owner_records: _OwnerRecords,
    listed_at: datetime,
) -> _ResourceGroupDecision:
    if resource_group.owner_type == OwnerType.INSTANCE:
        instance_model = owner_records.instances.get(resource_group.provider_ref)
        if instance_model is not None:
            return _get_instance_group_decision(
                orphan_cleanup_model, resource_group, instance_model, listed_at
            )
        job_model = owner_records.jobs.get(resource_group.provider_ref)
        if job_model is not None:
            return _get_job_group_decision(
                orphan_cleanup_model, resource_group, job_model, listed_at
            )
        return _ResourceGroupDecision.IGNORE
    raise RuntimeError(f"Unknown resource_group.owner_type: {resource_group.owner_type}")


async def _handle_orphaned_resource_group(
    compute: ComputeWithResourceListingSupport,
    orphan_cleanup_model: OrphanCleanupModel,
    resource_group: ListedResourceGroup,
) -> _ResourceGroupDecision:
    if settings.ORPHAN_CLEANUP_MODE == OrphanCleanupMode.REPORT:
        sentry_sdk.capture_message(
            "Detected orphaned {} {} in {}/{}".format(
                resource_group.owner_type.value,
                resource_group.provider_ref,
                orphan_cleanup_model.backend.project.name,
                orphan_cleanup_model.backend.type.value,
            )
        )
        return _ResourceGroupDecision.ORPHAN
    try:
        await run_async(compute.delete_resource_group, resource_group)
    except Exception as e:
        if isinstance(e, NotYetTerminated):
            logger.info(
                "Cleanup of orphaned %s %s in %s/%s is skipped because the termination is in progress",
                resource_group.owner_type.value,
                resource_group.provider_ref,
                orphan_cleanup_model.backend.project.name,
                orphan_cleanup_model.backend.type.value,
            )
        elif isinstance(e, BackendError):
            logger.warning(
                "Cleanup of orphaned %s %s in %s/%s is skipped due to error: %s",
                resource_group.owner_type.value,
                resource_group.provider_ref,
                orphan_cleanup_model.backend.project.name,
                orphan_cleanup_model.backend.type.value,
                repr(e),
            )
        else:
            logger.exception(
                "Cleanup of orphaned %s %s in %s/%s is skipped because of unexpected exception",
                resource_group.owner_type.value,
                resource_group.provider_ref,
                orphan_cleanup_model.backend.project.name,
                orphan_cleanup_model.backend.type.value,
            )
        return _ResourceGroupDecision.SKIP
    logger.info(
        "Cleaned up orphaned %s %s in %s/%s",
        resource_group.owner_type.value,
        resource_group.provider_ref,
        orphan_cleanup_model.backend.project.name,
        orphan_cleanup_model.backend.type.value,
    )
    return _ResourceGroupDecision.ORPHAN


def _get_orphan_event(
    resource_group: ListedResourceGroup, owner_records: _OwnerRecords
) -> _OrphanEvent:
    assert resource_group.owner_type == OwnerType.INSTANCE
    owner_model = owner_records.instances.get(resource_group.provider_ref)
    if owner_model is None:
        owner_model = owner_records.jobs[resource_group.provider_ref]
    return _OrphanEvent(
        message=_get_orphan_event_message(resource_group),
        target=events.Target.from_model(owner_model),
    )


def _get_orphan_event_message(resource_group: ListedResourceGroup) -> str:
    # Built from the required fields so that the message is useful
    # even if the backend fills `description` poorly.
    if settings.ORPHAN_CLEANUP_MODE == OrphanCleanupMode.REPORT:
        action = "found"
    else:
        action = "deleted"
    location = resource_group.backend.value
    if resource_group.region is not None:
        location += f"/{resource_group.region}"
    message = (
        f"Orphaned resources {action} in {location}, provider_ref {resource_group.provider_ref}"
    )
    if resource_group.primary_id is not None:
        message += f", {resource_group.owner_type.value} id {resource_group.primary_id}"
    if resource_group.description:
        message += f": {resource_group.description}"
    return message


_STUCK_PENDING_THRESHOLD = timedelta(hours=1)


def _get_instance_group_decision(
    orphan_cleanup_model: OrphanCleanupModel,
    resource_group: ListedResourceGroup,
    instance_model: InstanceModel,
    listed_at: datetime,
) -> _ResourceGroupDecision:
    if instance_model.status == InstanceStatus.PENDING:
        if (
            resource_group.created_at is not None
            and resource_group.created_at < listed_at - _STUCK_PENDING_THRESHOLD
        ):
            # Stuck pending instances are unexpected. If this changes,
            # we may treat them as orphans instead of error log and skip.
            logger.error(
                "Resource group %s in %s/%s was created at %s for instance %s"
                " that is still pending. The instance may be stuck in pending.",
                resource_group.provider_ref,
                orphan_cleanup_model.backend.project.name,
                orphan_cleanup_model.backend.type.value,
                resource_group.created_at,
                instance_model.name,
            )
        return _ResourceGroupDecision.SKIP
    if instance_model.status == InstanceStatus.TERMINATING:
        return _ResourceGroupDecision.SKIP
    if instance_model.status == InstanceStatus.TERMINATED:
        return _ResourceGroupDecision.ORPHAN
    provisioning_data = get_instance_provisioning_data(instance_model)
    if provisioning_data is None:
        logger.error(
            "Failed to classify resource group %s in %s/%s: provisioning_data is None for active instance",
            instance_model.name,
            orphan_cleanup_model.backend.project.name,
            orphan_cleanup_model.backend.type.value,
        )
        return _ResourceGroupDecision.IGNORE
    if (
        provisioning_data.get_base_backend() != resource_group.backend
        or provisioning_data.instance_id != resource_group.primary_id
    ):
        return _ResourceGroupDecision.ORPHAN
    return _ResourceGroupDecision.TRACKED


def _get_job_group_decision(
    orphan_cleanup_model: OrphanCleanupModel,
    resource_group: ListedResourceGroup,
    job_model: JobModel,
    listed_at: datetime,
) -> _ResourceGroupDecision:
    # Successful job provisioning moves the job out of submitted
    # and sets its `provider_ref` on the instance in the same transaction.
    # So a submitted job may be provisioning the resources right now,
    # while resources of a job in any other status are left from failed provisioning.
    if job_model.status == JobStatus.SUBMITTED:
        if (
            resource_group.created_at is not None
            and resource_group.created_at < listed_at - _STUCK_PENDING_THRESHOLD
        ):
            logger.error(
                "Resource group %s in %s/%s was created at %s for job %s"
                " that is still submitted. The job may be stuck in submitted.",
                resource_group.provider_ref,
                orphan_cleanup_model.backend.project.name,
                orphan_cleanup_model.backend.type.value,
                resource_group.created_at,
                job_model.job_name,
            )
        return _ResourceGroupDecision.SKIP
    return _ResourceGroupDecision.ORPHAN


def _get_failed_cleanup_process_result(
    orphan_cleanup_model: OrphanCleanupModel,
) -> _ProcessResult:
    return _ProcessResult(
        update_map=_OrphanCleanupUpdateMap(
            cleanup_attempt=orphan_cleanup_model.cleanup_attempt + 1
        )
    )


def _get_skips_cleanup_process_result(
    orphan_cleanup_model: OrphanCleanupModel,
) -> _ProcessResult:
    return _ProcessResult(
        update_map=_OrphanCleanupUpdateMap(
            cleanup_attempt=orphan_cleanup_model.cleanup_attempt + 1
        )
    )


def _get_partial_cleanup_process_result() -> _ProcessResult:
    # The backend stays eligible since `clean_at` is not updated.
    # It's retried after the cleanup interval rather than backed off,
    # so that the listed parts are cleaned up as usual while other parts fail.
    return _ProcessResult(update_map=_OrphanCleanupUpdateMap(cleanup_attempt=0))


def _get_success_cleanup_process_result(listed_at: datetime) -> _ProcessResult:
    return _ProcessResult(
        update_map=_OrphanCleanupUpdateMap(
            cleanup_attempt=0,
            clean_at=listed_at,
            clean_mode=settings.ORPHAN_CLEANUP_MODE,
        )
    )


async def _apply_process_result(
    item: PipelineItem, process_context: _ProcessContext, result: _ProcessResult
):
    update_map = _OrphanCleanupUpdateMap()
    update_map.update(result.update_map)
    set_processed_update_map_fields(update_map)
    set_unlock_update_map_fields(update_map)
    async with get_session_ctx() as session:
        now = get_current_datetime()
        resolve_now_placeholders(update_map, now=now)
        res = await session.execute(
            update(OrphanCleanupModel)
            .where(
                OrphanCleanupModel.id == item.id,
                OrphanCleanupModel.lock_token == item.lock_token,
            )
            .values(**update_map)
            .returning(OrphanCleanupModel.id)
        )
        updated_ids = list(res.scalars().all())
        if len(updated_ids) == 0:
            log_lock_token_changed_after_processing(logger, item)
            return
        for orphan_event in result.orphan_events:
            events.emit(
                session,
                orphan_event.message,
                actor=events.SystemActor(),
                targets=[orphan_event.target],
            )
