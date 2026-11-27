import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Optional, Sequence

from sqlalchemy import or_, select, update
from sqlalchemy.orm import joinedload, load_only

from dstack._internal.core.backends.base.compute import ComputeWithVolumeSupport
from dstack._internal.core.errors import (
    BackendError,
    VolumeDeletionPending,
    VolumeProvisioningError,
    VolumeProvisioningPending,
)
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.volumes import VolumeProvisioningData, VolumeStatus
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
    log_lock_token_mismatch,
    resolve_now_placeholders,
    set_processed_update_map_fields,
    set_unlock_update_map_fields,
)
from dstack._internal.server.db import get_db, get_session_ctx
from dstack._internal.server.models import (
    FleetModel,
    InstanceModel,
    ProjectModel,
    UserModel,
    VolumeAttachmentModel,
    VolumeModel,
)
from dstack._internal.server.services import events
from dstack._internal.server.services.backends import cache as backends_cache
from dstack._internal.server.services.locking import get_locker
from dstack._internal.server.services.pipelines import PipelineHinterProtocol
from dstack._internal.server.services.volumes import (
    emit_volume_status_change_event,
    volume_model_to_volume,
)
from dstack._internal.server.utils import tracing
from dstack._internal.utils.common import get_current_datetime, run_async
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class VolumePipelineItem(PipelineItem):
    status: VolumeStatus
    to_be_deleted: bool


class VolumePipeline(Pipeline[VolumePipelineItem]):
    def __init__(
        self,
        workers_num: int = 10,
        queue_lower_limit_factor: float = 0.5,
        queue_upper_limit_factor: float = 2.0,
        min_processing_interval: timedelta = timedelta(seconds=15),
        lock_timeout: timedelta = timedelta(seconds=30),
        heartbeat_trigger: timedelta = timedelta(seconds=15),
        *,
        pipeline_hinter: PipelineHinterProtocol,
    ) -> None:
        super().__init__(
            workers_num=workers_num,
            queue_lower_limit_factor=queue_lower_limit_factor,
            queue_upper_limit_factor=queue_upper_limit_factor,
            min_processing_interval=min_processing_interval,
            lock_timeout=lock_timeout,
            heartbeat_trigger=heartbeat_trigger,
        )
        self.__heartbeater = Heartbeater[VolumePipelineItem](
            model_type=VolumeModel,
            lock_timeout=self._lock_timeout,
            heartbeat_trigger=self._heartbeat_trigger,
        )
        self.__fetcher = VolumeFetcher(
            queue=self._queue,
            queue_desired_minsize=self._queue_desired_minsize,
            min_processing_interval=self._min_processing_interval,
            lock_timeout=self._lock_timeout,
            heartbeater=self._heartbeater,
        )
        self.__workers = [
            VolumeWorker(
                queue=self._queue,
                heartbeater=self._heartbeater,
                pipeline_hinter=pipeline_hinter,
            )
            for _ in range(self._workers_num)
        ]

    @property
    def hint_fetch_model_name(self) -> str:
        return VolumeModel.__name__

    @property
    def _heartbeater(self) -> Heartbeater[VolumePipelineItem]:
        return self.__heartbeater

    @property
    def _fetcher(self) -> Fetcher[VolumePipelineItem]:
        return self.__fetcher

    @property
    def _workers(self) -> Sequence["VolumeWorker"]:
        return self.__workers


class VolumeFetcher(Fetcher[VolumePipelineItem]):
    def __init__(
        self,
        queue: asyncio.Queue[VolumePipelineItem],
        queue_desired_minsize: int,
        min_processing_interval: timedelta,
        lock_timeout: timedelta,
        heartbeater: Heartbeater[VolumePipelineItem],
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

    @tracing.instrument_pipeline_task("VolumeFetcher.fetch")
    async def fetch(self, limit: int) -> list[VolumePipelineItem]:
        volume_lock, _ = get_locker(get_db().dialect_name).get_lockset(VolumeModel.__tablename__)
        async with volume_lock:
            async with get_session_ctx() as session:
                now = get_current_datetime()
                res = await session.execute(
                    select(VolumeModel)
                    .where(
                        or_(
                            VolumeModel.status.in_(
                                [VolumeStatus.SUBMITTED, VolumeStatus.PROVISIONING]
                            ),
                            VolumeModel.to_be_deleted == True,
                        ),
                        VolumeModel.deleted == False,
                        or_(
                            VolumeModel.last_processed_at <= now - self._min_processing_interval,
                            VolumeModel.last_processed_at == VolumeModel.created_at,
                        ),
                        or_(
                            VolumeModel.lock_expires_at.is_(None),
                            VolumeModel.lock_expires_at < now,
                        ),
                        or_(
                            VolumeModel.lock_owner.is_(None),
                            VolumeModel.lock_owner == VolumePipeline.__name__,
                        ),
                    )
                    .order_by(VolumeModel.last_processed_at.asc())
                    .limit(limit)
                    .with_for_update(skip_locked=True, key_share=True, of=VolumeModel)
                    .options(
                        load_only(
                            VolumeModel.id,
                            VolumeModel.lock_token,
                            VolumeModel.lock_expires_at,
                            VolumeModel.status,
                            VolumeModel.to_be_deleted,
                        )
                    )
                )
                volume_models = list(res.scalars().all())
                lock_expires_at = get_current_datetime() + self._lock_timeout
                lock_token = uuid.uuid4()
                items = []
                for volume_model in volume_models:
                    prev_lock_expired = volume_model.lock_expires_at is not None
                    volume_model.lock_expires_at = lock_expires_at
                    volume_model.lock_token = lock_token
                    volume_model.lock_owner = VolumePipeline.__name__
                    items.append(
                        VolumePipelineItem(
                            __tablename__=VolumeModel.__tablename__,
                            id=volume_model.id,
                            lock_expires_at=lock_expires_at,
                            lock_token=lock_token,
                            prev_lock_expired=prev_lock_expired,
                            status=volume_model.status,
                            to_be_deleted=volume_model.to_be_deleted,
                        )
                    )
                await session.commit()
        return items


class VolumeWorker(Worker[VolumePipelineItem]):
    def __init__(
        self,
        queue: asyncio.Queue[VolumePipelineItem],
        heartbeater: Heartbeater[VolumePipelineItem],
        pipeline_hinter: PipelineHinterProtocol,
    ) -> None:
        super().__init__(
            queue=queue,
            heartbeater=heartbeater,
            pipeline_hinter=pipeline_hinter,
        )

    @tracing.instrument_pipeline_task("VolumeWorker.process")
    async def process(self, item: VolumePipelineItem):
        volume_model = await _refetch_locked_volume(item)
        if volume_model is None:
            log_lock_token_mismatch(logger, item)
            return

        if item.to_be_deleted:
            result = await _process_to_be_deleted_volume(volume_model)
        elif item.status in (VolumeStatus.SUBMITTED, VolumeStatus.PROVISIONING):
            result = await _process_submitted_volume(volume_model)
        else:
            return

        await _apply_process_result(item=item, volume_model=volume_model, result=result)


async def _refetch_locked_volume(item: VolumePipelineItem) -> Optional[VolumeModel]:
    async with get_session_ctx() as session:
        res = await session.execute(
            select(VolumeModel)
            .where(
                VolumeModel.id == item.id,
                VolumeModel.lock_token == item.lock_token,
            )
            .options(joinedload(VolumeModel.project).joinedload(ProjectModel.backends))
            .options(joinedload(VolumeModel.user).load_only(UserModel.name))
            .options(
                joinedload(VolumeModel.attachments)
                .joinedload(VolumeAttachmentModel.instance)
                .joinedload(InstanceModel.fleet)
                .load_only(FleetModel.name)
            )
        )
        return res.unique().scalar_one_or_none()


async def _apply_process_result(
    item: VolumePipelineItem,
    volume_model: VolumeModel,
    result: "_ProcessResult",
):
    update_map = _VolumeUpdateMap()
    update_map.update(result.update_map)
    set_processed_update_map_fields(update_map)
    set_unlock_update_map_fields(update_map)

    async with get_session_ctx() as session:
        resolve_now_placeholders(update_map, now=get_current_datetime())
        res = await session.execute(
            update(VolumeModel)
            .where(
                VolumeModel.id == volume_model.id,
                VolumeModel.lock_token == volume_model.lock_token,
            )
            .values(**update_map)
            .returning(VolumeModel.id)
        )
        updated_ids = list(res.scalars().all())
        if len(updated_ids) == 0:
            log_lock_token_changed_after_processing(logger, item)
            if item.status == VolumeStatus.SUBMITTED:
                # TODO: Clean up volume.
                pass
            return
        if update_map.get("deleted"):
            events.emit(
                session,
                "Volume deleted",
                actor=events.SystemActor(),
                targets=[events.Target.from_model(volume_model)],
            )
        else:
            emit_volume_status_change_event(
                session=session,
                volume_model=volume_model,
                old_status=volume_model.status,
                new_status=update_map.get("status", volume_model.status),
                status_message=update_map.get("status_message", volume_model.status_message),
            )


class _VolumeUpdateMap(ItemUpdateMap, total=False):
    status: VolumeStatus
    status_message: Optional[str]
    volume_provisioning_data: str
    deleted: bool
    deleted_at: UpdateMapDateTime


@dataclass
class _ProcessResult:
    update_map: _VolumeUpdateMap = field(default_factory=_VolumeUpdateMap)


async def _process_submitted_volume(volume_model: VolumeModel) -> _ProcessResult:
    volume = volume_model_to_volume(volume_model)
    managed_create = volume.get_backend() == BackendType.MASSEDCOMPUTE and not volume.external
    first_create = managed_create and volume.status == VolumeStatus.SUBMITTED
    async with backends_cache.lease_project_backend_by_type(
        project=volume_model.project,
        backend_type=volume.configuration.backend,
        overrides=True,
    ) as backend:
        if backend is None:
            logger.error(
                "Failed to process volume %s. Backend %s not available.",
                volume.name,
                volume.configuration.backend.value,
            )
            update_map = _VolumeUpdateMap(status_message="Backend not available")
            if not managed_create:
                update_map["status"] = VolumeStatus.FAILED
            return _ProcessResult(update_map=update_map)
        compute = backend.compute()
        assert isinstance(compute, ComputeWithVolumeSupport)
        # The winning caller keeps its SUBMITTED snapshot and may send one POST.
        # A replacement reads PROVISIONING and can only look up the original create.
        if first_create and not await _mark_volume_provisioning(volume_model):
            return _ProcessResult()
        try:
            if volume.configuration.is_external:
                logger.info("Registering external volume %s", volume_model.name)
                vpd = await run_async(
                    compute.register_volume,
                    volume=volume,
                )
            else:
                logger.info("Provisioning new volume %s", volume_model.name)
                vpd = await run_async(
                    compute.create_volume,
                    volume=volume,
                )
        except (VolumeProvisioningPending, VolumeProvisioningError) as e:
            update_map = _get_volume_retry_update(str(e), e.volume_id, volume.get_backend())
            # Rejection of a retry cannot rule out an earlier create with a lost response.
            if isinstance(e, VolumeProvisioningError) and (
                first_create or not managed_create or e.volume_id is not None
            ):
                update_map["status"] = VolumeStatus.FAILED
            return _ProcessResult(update_map=update_map)
        except BackendError as e:
            logger.info("Failed to create volume %s: %s", volume_model.name, repr(e))
            status_message = f"Backend error: {repr(e)}"
            if len(e.args) > 0:
                status_message = str(e.args[0])
            update_map = _VolumeUpdateMap(status_message=status_message)
            if not managed_create or volume.volume_id is not None:
                update_map["status"] = VolumeStatus.FAILED
            return _ProcessResult(update_map=update_map)
        except Exception as e:
            logger.exception("Got exception when creating volume %s", volume_model.name)
            if managed_create:
                return _ProcessResult(update_map={"status_message": f"Unexpected error: {e!r}"})
            return _ProcessResult(
                update_map={
                    "status": VolumeStatus.FAILED,
                    "status_message": f"Unexpected error: {repr(e)}",
                }
            )

    logger.info("Added new volume %s", volume_model.name)
    update_map = _VolumeUpdateMap(
        status=VolumeStatus.ACTIVE,
        volume_provisioning_data=vpd.model_dump_json(),
    )
    if volume.get_backend() == BackendType.MASSEDCOMPUTE and volume.status_message is not None:
        update_map["status_message"] = None
    return _ProcessResult(update_map=update_map)


async def _mark_volume_provisioning(volume_model: VolumeModel) -> bool:
    # A create may outlive its worker. Record that it needs reconciliation before calling out.
    async with get_session_ctx() as session:
        result = await session.execute(
            update(VolumeModel)
            .where(
                VolumeModel.id == volume_model.id,
                VolumeModel.lock_token == volume_model.lock_token,
                VolumeModel.status == VolumeStatus.SUBMITTED,
                VolumeModel.to_be_deleted == False,
            )
            .values(status=VolumeStatus.PROVISIONING)
            .returning(VolumeModel.id)
        )
        if result.scalar_one_or_none() is None:
            return False
        emit_volume_status_change_event(
            session, volume_model, VolumeStatus.SUBMITTED, VolumeStatus.PROVISIONING, None
        )
    volume_model.status = VolumeStatus.PROVISIONING
    return True


async def _process_to_be_deleted_volume(volume_model: VolumeModel) -> _ProcessResult:
    volume = volume_model_to_volume(volume_model)
    if volume.external:
        return _get_deleted_result()
    managed_massedcompute = volume.get_backend() == BackendType.MASSEDCOMPUTE
    if volume.provisioning_data is not None:
        backend_type = volume.provisioning_data.backend
    elif managed_massedcompute and volume.status == VolumeStatus.PROVISIONING:
        # A previous create may have succeeded without returning its ID. A FAILED
        # managed volume with no ID was definitively rejected on its first attempt.
        backend_type = volume.get_backend()
    else:
        return _get_deleted_result()
    if backend_type is None:
        logger.error(
            f"Failed to delete volume {volume_model.name}. volume.provisioning_data.backend is None."
        )
        return _get_deleted_result()
    async with backends_cache.lease_project_backend_by_type(
        project=volume_model.project,
        backend_type=backend_type,
    ) as backend:
        if backend is None:
            if managed_massedcompute:
                return _ProcessResult(update_map={"status_message": "Backend not available"})
            # TODO: Retry deletion
            logger.error(
                f"Failed to delete volume {volume_model.name}. Backend {volume.configuration.backend} not available."
                " Please terminate it manually to avoid unexpected charges.",
            )
            return _get_deleted_result()
        compute = backend.compute()
        assert isinstance(compute, ComputeWithVolumeSupport)
        try:
            await run_async(
                compute.delete_volume,
                volume=volume,
            )
        except VolumeDeletionPending as e:
            logger.info("Volume %s deletion pending: %s", volume.name, e)
            return _ProcessResult(
                update_map=_get_volume_retry_update(str(e), e.volume_id, volume.get_backend())
            )
        except Exception as e:
            if managed_massedcompute:
                logger.exception("Could not confirm deletion of volume %s", volume.name)
                return _ProcessResult(update_map={"status_message": f"Deletion unconfirmed: {e}"})
            # TODO: Retry deletion
            logger.exception(
                "Got exception when deleting volume %s. Please terminate it manually to avoid unexpected charges.",
                volume.name,
            )
    return _get_deleted_result()


def _get_volume_retry_update(
    message: str, volume_id: Optional[str], backend: BackendType
) -> _VolumeUpdateMap:
    update_map = _VolumeUpdateMap(status_message=message)
    if volume_id is not None:
        update_map["volume_provisioning_data"] = VolumeProvisioningData(
            backend=backend, volume_id=volume_id, size_gb=None
        ).model_dump_json()
    return update_map


def _get_deleted_result() -> _ProcessResult:
    return _ProcessResult(
        update_map={
            "deleted": True,
            "deleted_at": NOW_PLACEHOLDER,
        }
    )
