import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, Sequence, TypedDict

import httpx
from sqlalchemy import delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, load_only

from dstack._internal.core.backends.base.backend import Backend
from dstack._internal.core.backends.base.compute import ComputeWithVolumeSupport
from dstack._internal.core.consts import DSTACK_SHIM_HTTP_PORT
from dstack._internal.core.errors import BackendError, GatewayError, SSHError
from dstack._internal.core.models.instances import InstanceStatus, InstanceTerminationReason
from dstack._internal.core.models.runs import (
    JobProvisioningData,
    JobRuntimeData,
    JobSpec,
    JobStatus,
    JobTerminationReason,
    RunTerminationReason,
)
from dstack._internal.server import settings
from dstack._internal.server.background.pipeline_tasks.base import (
    NOW_PLACEHOLDER,
    Fetcher,
    Heartbeater,
    ItemUpdateMap,
    Pipeline,
    PipelineItem,
    UpdateMapDateTime,
    Worker,
    log_lock_token_changed_after_processing,
    log_lock_token_changed_on_reset,
    log_lock_token_mismatch,
    resolve_now_placeholders,
    set_processed_update_map_fields,
    set_unlock_update_map_fields,
)
from dstack._internal.server.db import get_db, get_session_ctx
from dstack._internal.server.models import (
    InstanceModel,
    JobModel,
    ProjectModel,
    RunModel,
    VolumeAttachmentModel,
    VolumeModel,
)
from dstack._internal.server.services import backends as backends_services
from dstack._internal.server.services import events
from dstack._internal.server.services.gateways import get_or_add_gateway_connection
from dstack._internal.server.services.instances import (
    emit_instance_status_change_event,
    get_instance_ssh_private_keys,
)
from dstack._internal.server.services.jobs import (
    emit_job_status_change_event,
    get_job_provisioning_data,
    get_job_runtime_data,
    get_job_spec,
)
from dstack._internal.server.services.locking import get_locker
from dstack._internal.server.services.logging import fmt
from dstack._internal.server.services.runner import client
from dstack._internal.server.services.runner.ssh import runner_ssh_tunnel
from dstack._internal.server.services.volumes import (
    volume_model_to_volume,
)
from dstack._internal.server.utils import sentry_utils
from dstack._internal.utils import common
from dstack._internal.utils.common import get_current_datetime, get_or_error
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class JobTerminatingPipelineItem(PipelineItem):
    volumes_detached_at: Optional[datetime]


class JobTerminatingPipeline(Pipeline[JobTerminatingPipelineItem]):
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
        self.__heartbeater = Heartbeater[JobTerminatingPipelineItem](
            model_type=JobModel,
            lock_timeout=self._lock_timeout,
            heartbeat_trigger=self._heartbeat_trigger,
        )
        self.__fetcher = JobTerminatingFetcher(
            queue=self._queue,
            queue_desired_minsize=self._queue_desired_minsize,
            min_processing_interval=self._min_processing_interval,
            lock_timeout=self._lock_timeout,
            heartbeater=self._heartbeater,
        )
        self.__workers = [
            JobTerminatingWorker(queue=self._queue, heartbeater=self._heartbeater)
            for _ in range(self._workers_num)
        ]

    @property
    def hint_fetch_model_name(self) -> str:
        return JobModel.__name__

    @property
    def _heartbeater(self) -> Heartbeater[JobTerminatingPipelineItem]:
        return self.__heartbeater

    @property
    def _fetcher(self) -> Fetcher[JobTerminatingPipelineItem]:
        return self.__fetcher

    @property
    def _workers(self) -> Sequence["JobTerminatingWorker"]:
        return self.__workers


class JobTerminatingFetcher(Fetcher[JobTerminatingPipelineItem]):
    def __init__(
        self,
        queue: asyncio.Queue[JobTerminatingPipelineItem],
        queue_desired_minsize: int,
        min_processing_interval: timedelta,
        lock_timeout: timedelta,
        heartbeater: Heartbeater[JobTerminatingPipelineItem],
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

    @sentry_utils.instrument_named_task("pipeline_tasks.JobTerminatingFetcher.fetch")
    async def fetch(self, limit: int) -> list[JobTerminatingPipelineItem]:
        job_lock, _ = get_locker(get_db().dialect_name).get_lockset(JobModel.__tablename__)
        async with job_lock:
            async with get_session_ctx() as session:
                now = get_current_datetime()
                res = await session.execute(
                    select(JobModel)
                    .where(
                        JobModel.status == JobStatus.TERMINATING,
                        or_(
                            JobModel.remove_at.is_(None),
                            JobModel.remove_at < now,
                        ),
                        JobModel.last_processed_at <= now - self._min_processing_interval,
                        or_(
                            JobModel.lock_expires_at.is_(None),
                            JobModel.lock_expires_at < now,
                        ),
                        or_(
                            JobModel.lock_owner.is_(None),
                            JobModel.lock_owner == JobTerminatingPipeline.__name__,
                        ),
                    )
                    .order_by(JobModel.last_processed_at.asc())
                    .limit(limit)
                    .with_for_update(skip_locked=True, key_share=True, of=JobModel)
                    .options(
                        load_only(
                            JobModel.id,
                            JobModel.lock_token,
                            JobModel.lock_expires_at,
                            JobModel.volumes_detached_at,
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
                    job_model.lock_owner = JobTerminatingPipeline.__name__
                    items.append(
                        JobTerminatingPipelineItem(
                            __tablename__=JobModel.__tablename__,
                            id=job_model.id,
                            lock_expires_at=lock_expires_at,
                            lock_token=lock_token,
                            prev_lock_expired=prev_lock_expired,
                            volumes_detached_at=job_model.volumes_detached_at,
                        )
                    )
                await session.commit()
        return items


class JobTerminatingWorker(Worker[JobTerminatingPipelineItem]):
    def __init__(
        self,
        queue: asyncio.Queue[JobTerminatingPipelineItem],
        heartbeater: Heartbeater[JobTerminatingPipelineItem],
    ) -> None:
        super().__init__(
            queue=queue,
            heartbeater=heartbeater,
        )

    @sentry_utils.instrument_named_task("pipeline_tasks.JobTerminatingWorker.process")
    async def process(self, item: JobTerminatingPipelineItem):
        async with get_session_ctx() as session:
            job_model = await _refetch_locked_job(session=session, item=item)
            if job_model is None:
                log_lock_token_mismatch(logger, item)
                return

            instance_model: Optional[InstanceModel] = None
            if job_model.used_instance_id is not None:
                instance_model = await _lock_related_instance(
                    session=session,
                    item=item,
                    instance_id=job_model.used_instance_id,
                )
                if instance_model is None:
                    await _reset_job_lock_for_retry(session=session, item=item)
                    return

        if job_model.volumes_detached_at is None:
            result = await _process_terminating_job(
                job_model=job_model,
                instance_model=instance_model,
            )
        else:
            result = await _process_job_volumes_detaching(
                job_model=job_model,
                instance_model=get_or_error(instance_model),
            )

        set_processed_update_map_fields(result.job_update_map)
        set_unlock_update_map_fields(result.job_update_map)
        if instance_model is not None:
            if result.instance_update_map is None:
                result.instance_update_map = _InstanceUpdateMap()
            instance_update_map = result.instance_update_map
            set_processed_update_map_fields(instance_update_map)
            set_unlock_update_map_fields(instance_update_map)
        await _apply_process_result(
            item=item,
            job_model=job_model,
            instance_model=instance_model,
            result=result,
        )


class _JobUpdateMap(ItemUpdateMap, total=False):
    status: JobStatus
    termination_reason: Optional[JobTerminationReason]
    termination_reason_message: Optional[str]
    instance_id: Optional[uuid.UUID]
    volumes_detached_at: UpdateMapDateTime
    registered: bool


class _InstanceUpdateMap(ItemUpdateMap, total=False):
    status: InstanceStatus
    termination_reason: Optional[InstanceTerminationReason]
    termination_reason_message: Optional[str]
    busy_blocks: int
    last_job_processed_at: UpdateMapDateTime


class _VolumeUpdateRow(TypedDict):
    id: uuid.UUID
    last_job_processed_at: UpdateMapDateTime


@dataclass
class _ProcessResult:
    job_update_map: _JobUpdateMap = field(default_factory=_JobUpdateMap)
    instance_update_map: Optional[_InstanceUpdateMap] = None
    volume_update_rows: list[_VolumeUpdateRow] = field(default_factory=list)
    detached_volume_ids: set[uuid.UUID] = field(default_factory=set)
    unassign_event_message: Optional[str] = None
    emit_unregister_replica_event: bool = False
    unregister_gateway_target: Optional[events.Target] = None


@dataclass
class _VolumeDetachResult:
    all_detached: bool
    detached_volume_ids: set[uuid.UUID] = field(default_factory=set)
    set_volumes_detached_at: bool = False


async def _refetch_locked_job(
    session: AsyncSession, item: JobTerminatingPipelineItem
) -> Optional[JobModel]:
    res = await session.execute(
        select(JobModel)
        .where(
            JobModel.id == item.id,
            JobModel.lock_token == item.lock_token,
        )
        .options(
            joinedload(JobModel.run).load_only(
                RunModel.id,
                RunModel.project_id,
                RunModel.run_name,
                RunModel.gateway_id,
                RunModel.termination_reason,
            ),
            joinedload(JobModel.run)
            .joinedload(RunModel.project)
            .load_only(ProjectModel.id, ProjectModel.name),
        )
        .execution_options(populate_existing=True)
    )
    return res.unique().scalar_one_or_none()


async def _lock_related_instance(
    session: AsyncSession,
    item: JobTerminatingPipelineItem,
    instance_id: uuid.UUID,
) -> Optional[InstanceModel]:
    lock_owner = _get_related_instance_lock_owner(item.id)
    instance_lock, _ = get_locker(get_db().dialect_name).get_lockset(InstanceModel.__tablename__)
    async with instance_lock:
        res = await session.execute(
            select(InstanceModel)
            .where(
                InstanceModel.id == instance_id,
                or_(
                    InstanceModel.lock_expires_at.is_(None),
                    InstanceModel.lock_expires_at < get_current_datetime(),
                ),
                or_(
                    InstanceModel.lock_owner.is_(None),
                    InstanceModel.lock_owner == lock_owner,
                ),
            )
            .options(joinedload(InstanceModel.project).joinedload(ProjectModel.backends))
            .options(
                joinedload(InstanceModel.volume_attachments).joinedload(
                    VolumeAttachmentModel.volume
                )
            )
            .options(joinedload(InstanceModel.jobs).load_only(JobModel.id))
            .with_for_update(skip_locked=True, key_share=True, of=InstanceModel)
        )
        instance_model = res.unique().scalar_one_or_none()
        if instance_model is None:
            return None
        instance_model.lock_expires_at = item.lock_expires_at
        instance_model.lock_token = item.lock_token
        instance_model.lock_owner = lock_owner
        return instance_model


async def _load_job_volume_models(
    job_model: JobModel,
    instance_model: Optional[InstanceModel],
) -> list[VolumeModel]:
    if instance_model is None:
        return []
    jrd = get_job_runtime_data(job_model)
    volume_names = (
        jrd.volume_names
        if jrd and jrd.volume_names
        else [va.volume.name for va in instance_model.volume_attachments]
    )
    if len(volume_names) == 0:
        return []
    async with get_session_ctx() as session:
        res = await session.execute(
            select(VolumeModel)
            .where(
                VolumeModel.project_id == instance_model.project.id,
                VolumeModel.name.in_(volume_names),
                VolumeModel.deleted == False,
            )
            .options(joinedload(VolumeModel.project))
            .options(joinedload(VolumeModel.user))
            .options(
                joinedload(VolumeModel.attachments)
                .joinedload(VolumeAttachmentModel.instance)
                .joinedload(InstanceModel.fleet)
            )
        )
        return list(res.unique().scalars().all())


async def _reset_job_lock_for_retry(session: AsyncSession, item: JobTerminatingPipelineItem):
    res = await session.execute(
        update(JobModel)
        .where(
            JobModel.id == item.id,
            JobModel.lock_token == item.lock_token,
        )
        # Keep `lock_owner` so that `InstancePipeline` can check that the job is being locked
        # but unset `lock_expires_at` to process the item again ASAP (after `min_processing_interval`).
        # Unset `lock_token` so that heartbeater can no longer update the item.
        .values(
            lock_expires_at=None,
            lock_token=None,
            last_processed_at=get_current_datetime(),
        )
        .returning(JobModel.id)
    )
    updated_ids = list(res.scalars().all())
    if len(updated_ids) == 0:
        log_lock_token_changed_on_reset(logger)


async def _apply_process_result(
    item: JobTerminatingPipelineItem,
    job_model: JobModel,
    instance_model: Optional[InstanceModel],
    result: _ProcessResult,
) -> None:
    async with get_session_ctx() as session:
        now = get_current_datetime()
        related_instance_lock_owner = _get_related_instance_lock_owner(item.id)
        instance_update_map = result.instance_update_map
        if instance_model is None:
            instance_update_map = None
        resolve_now_placeholders(result.job_update_map, now=now)
        if instance_update_map is not None:
            resolve_now_placeholders(instance_update_map, now=now)
        if result.volume_update_rows:
            resolve_now_placeholders(result.volume_update_rows, now=now)

        res = await session.execute(
            update(JobModel)
            .where(
                JobModel.id == item.id,
                JobModel.lock_token == item.lock_token,
            )
            .values(**result.job_update_map)
            .returning(JobModel.id)
        )
        updated_ids = list(res.scalars().all())
        if len(updated_ids) == 0:
            log_lock_token_changed_after_processing(logger, item)
            if instance_model is not None:
                await _unlock_related_instance(
                    session=session,
                    item=item,
                    instance_id=instance_model.id,
                )
            return

        if instance_model is not None and instance_update_map is not None:
            res = await session.execute(
                update(InstanceModel)
                .where(
                    InstanceModel.id == instance_model.id,
                    InstanceModel.lock_token == item.lock_token,
                    InstanceModel.lock_owner == related_instance_lock_owner,
                )
                .values(**instance_update_map)
                .returning(InstanceModel.id)
            )
            updated_ids = list(res.scalars().all())
            if len(updated_ids) == 0:
                logger.error(
                    "Failed to update related instance %s for terminating job %s.",
                    instance_model.id,
                    item.id,
                )

        if result.volume_update_rows:
            await session.execute(update(VolumeModel), result.volume_update_rows)

        if result.detached_volume_ids and instance_model is not None:
            await session.execute(
                delete(VolumeAttachmentModel).where(
                    VolumeAttachmentModel.instance_id == instance_model.id,
                    VolumeAttachmentModel.volume_id.in_(result.detached_volume_ids),
                )
            )

        emit_job_status_change_event(
            session=session,
            job_model=job_model,
            old_status=job_model.status,
            new_status=result.job_update_map.get("status", job_model.status),
            termination_reason=result.job_update_map.get(
                "termination_reason", job_model.termination_reason
            ),
            termination_reason_message=result.job_update_map.get(
                "termination_reason_message",
                job_model.termination_reason_message,
            ),
        )

        if instance_model is not None and instance_update_map is not None:
            emit_instance_status_change_event(
                session=session,
                instance_model=instance_model,
                old_status=instance_model.status,
                new_status=instance_update_map.get("status", instance_model.status),
                termination_reason=instance_update_map.get(
                    "termination_reason",
                    instance_model.termination_reason,
                ),
                termination_reason_message=instance_update_map.get(
                    "termination_reason_message",
                    instance_model.termination_reason_message,
                ),
            )

        if result.unassign_event_message is not None and instance_model is not None:
            events.emit(
                session,
                result.unassign_event_message,
                actor=events.SystemActor(),
                targets=[
                    events.Target.from_model(job_model),
                    events.Target.from_model(instance_model),
                ],
            )

        if result.emit_unregister_replica_event:
            targets = [events.Target.from_model(job_model)]
            if result.unregister_gateway_target is not None:
                targets.append(result.unregister_gateway_target)
            events.emit(
                session,
                "Service replica unregistered from receiving requests",
                actor=events.SystemActor(),
                targets=targets,
            )


async def _unlock_related_instance(
    session: AsyncSession,
    item: JobTerminatingPipelineItem,
    instance_id: uuid.UUID,
) -> None:
    await session.execute(
        update(InstanceModel)
        .where(
            InstanceModel.id == instance_id,
            InstanceModel.lock_token == item.lock_token,
            InstanceModel.lock_owner == _get_related_instance_lock_owner(item.id),
        )
        .values(
            lock_expires_at=None,
            lock_token=None,
            lock_owner=None,
        )
    )


async def _process_terminating_job(
    job_model: JobModel,
    instance_model: Optional[InstanceModel],
) -> _ProcessResult:
    """
    Stops the job: tells shim to stop the container, detaches the job from the instance,
    and detaches volumes from the instance.
    Graceful stop should already be done by `process_terminating_run`.
    """
    instance_update_map = None if instance_model is None else _InstanceUpdateMap()
    result = _ProcessResult(instance_update_map=instance_update_map)

    if instance_model is None:
        await _unregister_replica_and_update_result(result=result, job_model=job_model)
        result.job_update_map["status"] = _get_job_termination_status(job_model)
        return result

    jrd = get_job_runtime_data(job_model)
    jpd = get_job_provisioning_data(job_model)
    if jpd is not None:
        logger.debug("%s: stopping container", fmt(job_model))
        ssh_private_keys = get_instance_ssh_private_keys(instance_model)
        if not await _stop_container(job_model, jpd, ssh_private_keys):
            logger.warning(
                (
                    "%s: could not stop container, possibly due to a communication error."
                    " See debug logs for details."
                    " Ignoring, can attempt to remove the container later"
                ),
                fmt(job_model),
            )

    (
        result.volume_update_rows,
        detach_result,
    ) = await _detach_job_volumes(
        job_model=job_model,
        instance_model=instance_model,
        job_provisioning_data=jpd,
    )
    result.detached_volume_ids = detach_result.detached_volume_ids
    if detach_result.set_volumes_detached_at:
        result.job_update_map["volumes_detached_at"] = NOW_PLACEHOLDER

    instance_update_map = get_or_error(result.instance_update_map)
    busy_blocks = instance_model.busy_blocks - _get_job_occupied_blocks(jrd)
    instance_update_map["busy_blocks"] = busy_blocks
    if instance_model.status != InstanceStatus.BUSY or jpd is None or not jpd.dockerized:
        if instance_model.status not in InstanceStatus.finished_statuses():
            instance_update_map["termination_reason"] = InstanceTerminationReason.JOB_FINISHED
            instance_update_map["status"] = InstanceStatus.TERMINATING
    elif not [j for j in instance_model.jobs if j.id != job_model.id]:
        instance_update_map["status"] = InstanceStatus.IDLE

    result.job_update_map["instance_id"] = None
    instance_update_map["last_job_processed_at"] = NOW_PLACEHOLDER
    result.unassign_event_message = (
        "Job unassigned from instance."
        f" Instance blocks: {busy_blocks}/{instance_model.total_blocks} busy"
    )

    await _unregister_replica_and_update_result(result=result, job_model=job_model)
    if detach_result.all_detached:
        result.job_update_map["status"] = _get_job_termination_status(job_model)
    return result


async def _process_job_volumes_detaching(
    job_model: JobModel,
    instance_model: InstanceModel,
) -> _ProcessResult:
    """
    Called after job's volumes have been soft detached to check if they are detached.
    Terminates the job when all the volumes are detached.
    If the volumes fail to detach, force detaches them.
    """
    result = _ProcessResult(instance_update_map=_InstanceUpdateMap())
    jpd = get_or_error(get_job_provisioning_data(job_model))
    (
        result.volume_update_rows,
        detach_result,
    ) = await _detach_job_volumes(
        job_model=job_model,
        instance_model=instance_model,
        job_provisioning_data=jpd,
    )
    result.detached_volume_ids = detach_result.detached_volume_ids
    if detach_result.all_detached:
        result.job_update_map["status"] = _get_job_termination_status(job_model)
    return result


async def _detach_job_volumes(
    job_model: JobModel,
    instance_model: InstanceModel,
    job_provisioning_data: Optional[JobProvisioningData],
) -> tuple[list[_VolumeUpdateRow], _VolumeDetachResult]:
    volume_models = await _load_job_volume_models(
        job_model=job_model, instance_model=instance_model
    )
    volume_update_rows = _get_volume_update_rows(volume_models)
    if len(volume_models) == 0:
        return volume_update_rows, _VolumeDetachResult(all_detached=True)

    if job_provisioning_data is None:
        return volume_update_rows, _VolumeDetachResult(all_detached=True)

    logger.info("Detaching volumes: %s", [v.name for v in volume_models])
    detach_result = await _detach_volumes_from_job_instance(
        job_model=job_model,
        instance_model=instance_model,
        volume_models=volume_models,
        jpd=job_provisioning_data,
        run_termination_reason=job_model.run.termination_reason,
    )
    return volume_update_rows, detach_result


async def _unregister_replica_and_update_result(
    result: _ProcessResult, job_model: JobModel
) -> None:
    result.unregister_gateway_target = await _unregister_replica(job_model=job_model)
    if job_model.registered:
        result.job_update_map["registered"] = False
        result.emit_unregister_replica_event = True


async def _unregister_replica(
    job_model: JobModel,
) -> Optional[events.Target]:
    if not job_model.registered:
        return None
    gateway_target = None
    run_model = job_model.run
    if run_model.gateway_id is not None:
        async with get_session_ctx() as session:
            gateway, conn = await get_or_add_gateway_connection(session, run_model.gateway_id)
            gateway_target = events.Target.from_model(gateway)
        try:
            logger.debug(
                "%s: unregistering replica from service %s", fmt(job_model), job_model.run_id.hex
            )
            async with conn.client() as client:
                await client.unregister_replica(
                    project=run_model.project.name,
                    run_name=run_model.run_name,
                    job_id=job_model.id,
                )
        except GatewayError as e:
            logger.warning("%s: unregistering replica from service: %s", fmt(job_model), e)
        except (httpx.RequestError, SSHError) as e:
            logger.debug("Gateway request failed", exc_info=True)
            # FIXME: Unhandled exception raised.
            # Handle and retry unregister with timeout.
            raise GatewayError(repr(e))
    return gateway_target


def _get_job_termination_status(job_model: JobModel) -> JobStatus:
    if job_model.termination_reason is not None:
        return job_model.termination_reason.to_status()
    return JobStatus.FAILED


def _get_volume_update_rows(volume_models: list[VolumeModel]) -> list[_VolumeUpdateRow]:
    return [
        {
            "id": volume_model.id,
            "last_job_processed_at": NOW_PLACEHOLDER,
        }
        for volume_model in volume_models
    ]


def _get_job_occupied_blocks(jrd: Optional[JobRuntimeData]) -> int:
    if jrd is not None and jrd.offer is not None:
        return jrd.offer.blocks
    return 1


async def _stop_container(
    job_model: JobModel,
    job_provisioning_data: JobProvisioningData,
    ssh_private_keys: tuple[str, Optional[str]],
) -> bool:
    if job_provisioning_data.dockerized:
        return await common.run_async(
            _shim_submit_stop,
            ssh_private_keys,
            job_provisioning_data,
            None,
            job_model,
        )
    return True


@runner_ssh_tunnel(ports=[DSTACK_SHIM_HTTP_PORT])
def _shim_submit_stop(ports: dict[int, int], job_model: JobModel) -> bool:
    shim_client = client.ShimClient(port=ports[DSTACK_SHIM_HTTP_PORT])

    resp = shim_client.healthcheck()
    if resp is None:
        logger.debug("%s: can't stop container, shim is not available yet", fmt(job_model))
        return False

    if shim_client.is_api_v2_supported():
        reason = (
            None if job_model.termination_reason is None else job_model.termination_reason.value
        )
        shim_client.terminate_task(
            task_id=job_model.id,
            reason=reason,
            message=job_model.termination_reason_message,
            timeout=0,
        )
        if not settings.SERVER_KEEP_SHIM_TASKS:
            shim_client.remove_task(task_id=job_model.id)
    else:
        shim_client.stop(force=True)
    return True


async def _detach_volumes_from_job_instance(
    job_model: JobModel,
    instance_model: InstanceModel,
    volume_models: list[VolumeModel],
    jpd: JobProvisioningData,
    run_termination_reason: Optional[RunTerminationReason],
) -> _VolumeDetachResult:
    job_spec = get_job_spec(job_model)
    backend = await backends_services.get_project_backend_by_type(
        project=instance_model.project,
        backend_type=jpd.backend,
    )
    if backend is None:
        logger.error(
            "Failed to detach volumes from %s. Backend not available.", instance_model.name
        )
        return _VolumeDetachResult(all_detached=False)

    detached_volume_ids = set()
    all_detached = True
    for volume_model in volume_models:
        detached = await _detach_volume_from_job_instance(
            backend=backend,
            job_model=job_model,
            jpd=jpd,
            job_spec=job_spec,
            instance_model=instance_model,
            volume_model=volume_model,
            run_termination_reason=run_termination_reason,
        )
        if detached:
            detached_volume_ids.add(volume_model.id)
        else:
            all_detached = False

    return _VolumeDetachResult(
        all_detached=all_detached,
        detached_volume_ids=detached_volume_ids,
        set_volumes_detached_at=job_model.volumes_detached_at is None,
    )


async def _detach_volume_from_job_instance(
    backend: Backend,
    job_model: JobModel,
    jpd: JobProvisioningData,
    job_spec: JobSpec,
    instance_model: InstanceModel,
    volume_model: VolumeModel,
    run_termination_reason: Optional[RunTerminationReason],
) -> bool:
    detached = True
    volume = volume_model_to_volume(volume_model)
    if volume.provisioning_data is None or not volume.provisioning_data.detachable:
        return detached
    compute = backend.compute()
    assert isinstance(compute, ComputeWithVolumeSupport)
    try:
        if job_model.volumes_detached_at is None:
            await common.run_async(
                compute.detach_volume,
                volume=volume,
                provisioning_data=jpd,
                force=False,
            )
            detached = await common.run_async(
                compute.is_volume_detached,
                volume=volume,
                provisioning_data=jpd,
            )
        else:
            detached = await common.run_async(
                compute.is_volume_detached,
                volume=volume,
                provisioning_data=jpd,
            )
            if not detached and _should_force_detach_volume(
                job_model=job_model,
                run_termination_reason=run_termination_reason,
                stop_duration=job_spec.stop_duration,
            ):
                logger.info(
                    "Force detaching volume %s from %s",
                    volume_model.name,
                    instance_model.name,
                )
                await common.run_async(
                    compute.detach_volume,
                    volume=volume,
                    provisioning_data=jpd,
                    force=True,
                )
    except BackendError as e:
        logger.error(
            "Failed to detach volume %s from %s: %s",
            volume_model.name,
            instance_model.name,
            repr(e),
        )
    except Exception:
        logger.exception(
            "Got exception when detaching volume %s from instance %s",
            volume_model.name,
            instance_model.name,
        )
    return detached


_MIN_FORCE_DETACH_WAIT_PERIOD = timedelta(seconds=60)


def _should_force_detach_volume(
    job_model: JobModel,
    run_termination_reason: Optional[RunTerminationReason],
    stop_duration: Optional[int],
) -> bool:
    now = get_current_datetime()
    return (
        job_model.volumes_detached_at is not None
        and now > job_model.volumes_detached_at + _MIN_FORCE_DETACH_WAIT_PERIOD
        and (
            job_model.termination_reason == JobTerminationReason.ABORTED_BY_USER
            or run_termination_reason == RunTerminationReason.ABORTED_BY_USER
            or stop_duration is not None
            and now > job_model.volumes_detached_at + timedelta(seconds=stop_duration)
        )
    )


def _get_related_instance_lock_owner(job_id: uuid.UUID) -> str:
    return f"{JobTerminatingPipeline.__name__}:{job_id}"
