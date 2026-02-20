import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Optional, Sequence

from sqlalchemy import or_, select, update
from sqlalchemy.orm import joinedload, load_only

from dstack._internal.core.errors import BackendError, BackendNotAvailable
from dstack._internal.core.models.gateways import GatewayStatus
from dstack._internal.server.background.pipeline_tasks.base import (
    Fetcher,
    Heartbeater,
    Pipeline,
    PipelineItem,
    UpdateMap,
    Worker,
    get_processed_update_map,
    get_unlock_update_map,
)
from dstack._internal.server.db import get_db, get_session_ctx
from dstack._internal.server.models import (
    GatewayComputeModel,
    GatewayModel,
    ProjectModel,
)
from dstack._internal.server.services import backends as backends_services
from dstack._internal.server.services import gateways as gateways_services
from dstack._internal.server.services.gateways import emit_gateway_status_change_event
from dstack._internal.server.services.gateways.pool import gateway_connections_pool
from dstack._internal.server.services.locking import get_locker
from dstack._internal.server.services.logging import fmt
from dstack._internal.utils.common import get_current_datetime
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class GatewayPipelineItem(PipelineItem):
    status: GatewayStatus


class GatewayPipeline(Pipeline[GatewayPipelineItem]):
    def __init__(
        self,
        workers_num: int = 10,
        queue_lower_limit_factor: float = 0.5,
        queue_upper_limit_factor: float = 2.0,
        min_processing_interval: timedelta = timedelta(seconds=15),
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
        self.__heartbeater = Heartbeater[GatewayPipelineItem](
            model_type=GatewayModel,
            lock_timeout=self._lock_timeout,
            heartbeat_trigger=self._heartbeat_trigger,
        )
        self.__fetcher = GatewayFetcher(
            queue=self._queue,
            queue_desired_minsize=self._queue_desired_minsize,
            min_processing_interval=self._min_processing_interval,
            lock_timeout=self._lock_timeout,
            heartbeater=self._heartbeater,
        )
        self.__workers = [
            GatewayWorker(queue=self._queue, heartbeater=self._heartbeater)
            for _ in range(self._workers_num)
        ]

    @property
    def hint_fetch_model_name(self) -> str:
        return GatewayModel.__name__

    @property
    def _heartbeater(self) -> Heartbeater[GatewayPipelineItem]:
        return self.__heartbeater

    @property
    def _fetcher(self) -> Fetcher[GatewayPipelineItem]:
        return self.__fetcher

    @property
    def _workers(self) -> Sequence["GatewayWorker"]:
        return self.__workers


class GatewayFetcher(Fetcher[GatewayPipelineItem]):
    def __init__(
        self,
        queue: asyncio.Queue[GatewayPipelineItem],
        queue_desired_minsize: int,
        min_processing_interval: timedelta,
        lock_timeout: timedelta,
        heartbeater: Heartbeater[GatewayPipelineItem],
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

    async def fetch(self, limit: int) -> list[GatewayPipelineItem]:
        gateway_lock, _ = get_locker(get_db().dialect_name).get_lockset(GatewayModel.__tablename__)
        async with gateway_lock:
            async with get_session_ctx() as session:
                now = get_current_datetime()
                res = await session.execute(
                    select(GatewayModel)
                    .where(
                        GatewayModel.status.in_(
                            [GatewayStatus.SUBMITTED, GatewayStatus.PROVISIONING]
                        ),
                        or_(
                            GatewayModel.last_processed_at <= now - self._min_processing_interval,
                            GatewayModel.last_processed_at == GatewayModel.created_at,
                        ),
                        or_(
                            GatewayModel.lock_expires_at.is_(None),
                            GatewayModel.lock_expires_at < now,
                        ),
                        or_(
                            GatewayModel.lock_owner.is_(None),
                            GatewayModel.lock_owner == GatewayPipeline.__name__,
                        ),
                    )
                    .order_by(GatewayModel.last_processed_at.asc())
                    .limit(limit)
                    .with_for_update(skip_locked=True, key_share=True)
                    .options(
                        load_only(
                            GatewayModel.id,
                            GatewayModel.status,
                            GatewayModel.lock_token,
                            GatewayModel.lock_expires_at,
                        )
                    )
                )
                gateway_models = list(res.scalars().all())
                lock_expires_at = get_current_datetime() + self._lock_timeout
                lock_token = uuid.uuid4()
                items = []
                for gateway_model in gateway_models:
                    prev_lock_expired = gateway_model.lock_expires_at is not None
                    gateway_model.lock_expires_at = lock_expires_at
                    gateway_model.lock_token = lock_token
                    gateway_model.lock_owner = GatewayPipeline.__name__
                    items.append(
                        GatewayPipelineItem(
                            __tablename__=GatewayModel.__tablename__,
                            id=gateway_model.id,
                            lock_expires_at=lock_expires_at,
                            lock_token=lock_token,
                            prev_lock_expired=prev_lock_expired,
                            status=gateway_model.status,
                        )
                    )
                await session.commit()
        return items


class GatewayWorker(Worker[GatewayPipelineItem]):
    def __init__(
        self,
        queue: asyncio.Queue[GatewayPipelineItem],
        heartbeater: Heartbeater[GatewayPipelineItem],
    ) -> None:
        super().__init__(
            queue=queue,
            heartbeater=heartbeater,
        )

    async def process(self, item: GatewayPipelineItem):
        if item.status == GatewayStatus.SUBMITTED:
            await _process_submitted_item(item)
        elif item.status == GatewayStatus.PROVISIONING:
            await _process_provisioning_item(item)


async def _process_submitted_item(item: GatewayPipelineItem):
    async with get_session_ctx() as session:
        res = await session.execute(
            select(GatewayModel)
            .where(
                GatewayModel.id == item.id,
                GatewayModel.lock_token == item.lock_token,
            )
            .options(joinedload(GatewayModel.project).joinedload(ProjectModel.backends))
        )
        gateway_model = res.unique().scalar_one_or_none()
        if gateway_model is None:
            logger.warning(
                "Failed to process %s item %s: lock_token mismatch."
                " The item is expected to be processed and updated on another fetch iteration.",
                item.__tablename__,
                item.id,
            )
            return

    result = await _process_submitted_gateway(gateway_model)
    update_map = result.update_map | get_processed_update_map() | get_unlock_update_map()
    async with get_session_ctx() as session:
        gateway_compute_model = result.gateway_compute_model
        if gateway_compute_model is not None:
            session.add(gateway_compute_model)
            await session.flush()
            update_map["gateway_compute_id"] = gateway_compute_model.id
        res = await session.execute(
            update(GatewayModel)
            .where(
                GatewayModel.id == gateway_model.id,
                GatewayModel.lock_token == gateway_model.lock_token,
            )
            .values(**update_map)
            .returning(GatewayModel.id)
        )
        updated_ids = list(res.scalars().all())
        if len(updated_ids) == 0:
            logger.warning(
                "Failed to update %s item %s after processing: lock_token changed."
                " The item is expected to be processed and updated on another fetch iteration.",
                item.__tablename__,
                item.id,
            )
            return
        emit_gateway_status_change_event(
            session=session,
            gateway_model=gateway_model,
            old_status=gateway_model.status,
            new_status=update_map.get("status", gateway_model.status),
            status_message=update_map.get("status_message", gateway_model.status_message),
        )


@dataclass
class _SubmittedResult:
    update_map: UpdateMap = field(default_factory=dict)
    gateway_compute_model: Optional[GatewayComputeModel] = None


async def _process_submitted_gateway(gateway_model: GatewayModel) -> _SubmittedResult:
    logger.info("%s: started gateway provisioning", fmt(gateway_model))
    configuration = gateways_services.get_gateway_configuration(gateway_model)
    try:
        (
            backend_model,
            backend,
        ) = await backends_services.get_project_backend_with_model_by_type_or_error(
            project=gateway_model.project, backend_type=configuration.backend
        )
    except BackendNotAvailable:
        return _SubmittedResult(
            update_map={
                "status": GatewayStatus.FAILED,
                "status_message": "Backend not available",
            }
        )
    try:
        gateway_compute_model = await gateways_services.create_gateway_compute(
            backend_compute=backend.compute(),
            project_name=gateway_model.project.name,
            configuration=configuration,
            backend_id=backend_model.id,
        )
        return _SubmittedResult(
            update_map={"status": GatewayStatus.PROVISIONING},
            gateway_compute_model=gateway_compute_model,
        )
    except BackendError as e:
        status_message = f"Backend error: {repr(e)}"
        if len(e.args) > 0:
            status_message = str(e.args[0])
        return _SubmittedResult(
            update_map={
                "status": GatewayStatus.FAILED,
                "status_message": status_message,
            }
        )
    except Exception as e:
        logger.exception("%s: got exception when creating gateway compute", fmt(gateway_model))
        return _SubmittedResult(
            update_map={
                "status": GatewayStatus.FAILED,
                "status_message": f"Unexpected error: {repr(e)}",
            }
        )


async def _process_provisioning_item(item: GatewayPipelineItem):
    async with get_session_ctx() as session:
        res = await session.execute(
            select(GatewayModel)
            .where(
                GatewayModel.id == item.id,
                GatewayModel.lock_token == item.lock_token,
            )
            .options(joinedload(GatewayModel.gateway_compute))
        )
        gateway_model = res.unique().scalar_one_or_none()
        if gateway_model is None:
            logger.warning(
                "Failed to process %s item %s: lock_token mismatch."
                " The item is expected to be processed and updated on another fetch iteration.",
                item.__tablename__,
                item.id,
            )
            return

    result = await _process_provisioning_gateway(gateway_model)
    update_map = result.gateway_update_map | get_processed_update_map() | get_unlock_update_map()
    async with get_session_ctx() as session:
        res = await session.execute(
            update(GatewayModel)
            .where(
                GatewayModel.id == gateway_model.id,
                GatewayModel.lock_token == gateway_model.lock_token,
            )
            .values(**update_map)
            .returning(GatewayModel.id)
        )
        updated_ids = list(res.scalars().all())
        if len(updated_ids) == 0:
            logger.warning(
                "Failed to update %s item %s after processing: lock_token changed."
                " The item is expected to be processed and updated on another fetch iteration.",
                item.__tablename__,
                item.id,
            )
            return
        emit_gateway_status_change_event(
            session=session,
            gateway_model=gateway_model,
            old_status=gateway_model.status,
            new_status=update_map.get("status", gateway_model.status),
            status_message=update_map.get("status_message", gateway_model.status_message),
        )
        if result.gateway_compute_update_map:
            res = await session.execute(
                update(GatewayComputeModel)
                .where(GatewayComputeModel.id == gateway_model.gateway_compute_id)
                .values(**result.gateway_compute_update_map)
                .returning(GatewayComputeModel.id)
            )
            updated_ids = list(res.scalars().all())
            if len(updated_ids) == 0:
                logger.error(
                    "Failed to update compute model %s for gateway %s."
                    " This is unexpected and may happen only if the compute model was manually deleted.",
                    gateway_model.id,
                    item.id,
                )


@dataclass
class _ProvisioningResult:
    gateway_update_map: UpdateMap = field(default_factory=dict)
    gateway_compute_update_map: UpdateMap = field(default_factory=dict)


async def _process_provisioning_gateway(gateway_model: GatewayModel) -> _ProvisioningResult:
    # Provisioning gateways must have compute.
    assert gateway_model.gateway_compute is not None

    # FIXME: problems caused by blocking on connect_to_gateway_with_retry and configure_gateway:
    # - cannot delete the gateway before it is provisioned because the DB model is locked
    # - connection retry counter is reset on server restart
    # - only one server replica is processing the gateway
    # Easy to fix by doing only one connection/configuration attempt per processing iteration. The
    # main challenge is applying the same provisioning model to the dstack Sky gateway to avoid
    # maintaining a different model for Sky.
    connection = await gateways_services.connect_to_gateway_with_retry(
        gateway_model.gateway_compute
    )
    if connection is None:
        return _ProvisioningResult(
            gateway_update_map={
                "status": GatewayStatus.FAILED,
                "status_message": "Failed to connect to gateway",
            },
            gateway_compute_update_map={"active": False},
        )
    try:
        await gateways_services.configure_gateway(connection)
    except Exception:
        logger.exception("%s: failed to configure gateway", fmt(gateway_model))
        await gateway_connections_pool.remove(gateway_model.gateway_compute.ip_address)
        return _ProvisioningResult(
            gateway_update_map={
                "status": GatewayStatus.FAILED,
                "status_message": "Failed to configure gateway",
            },
            gateway_compute_update_map={"active": False},
        )
    return _ProvisioningResult(
        gateway_update_map={"status": GatewayStatus.RUNNING},
    )
