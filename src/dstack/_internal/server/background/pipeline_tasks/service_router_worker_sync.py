import asyncio
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Sequence

from sqlalchemy import delete, or_, select, true, update
from sqlalchemy.orm import joinedload, load_only, selectinload

from dstack._internal.core.models.runs import JobStatus, RunStatus
from dstack._internal.server.background.pipeline_tasks.base import (
    Fetcher,
    Heartbeater,
    ItemUpdateMap,
    Pipeline,
    PipelineItem,
    Worker,
    log_lock_token_changed_after_processing,
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
    ServiceRouterWorkerSyncModel,
)
from dstack._internal.server.services.locking import get_locker
from dstack._internal.server.services.pipelines import PipelineHinterProtocol
from dstack._internal.server.services.router_worker_sync import (
    run_model_has_router_replica_group,
    sync_router_workers_for_run_model,
)
from dstack._internal.server.utils import sentry_utils
from dstack._internal.utils.common import get_current_datetime
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ServiceRouterWorkerSyncPipelineItem(PipelineItem):
    run_id: uuid.UUID


class ServiceRouterWorkerSyncPipeline(Pipeline[ServiceRouterWorkerSyncPipelineItem]):
    def __init__(
        self,
        workers_num: int = 8,
        queue_lower_limit_factor: float = 0.5,
        queue_upper_limit_factor: float = 2.0,
        min_processing_interval: timedelta = timedelta(seconds=5),
        lock_timeout: timedelta = timedelta(seconds=25),
        heartbeat_trigger: timedelta = timedelta(seconds=10),
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
        self.__heartbeater = Heartbeater[ServiceRouterWorkerSyncPipelineItem](
            model_type=ServiceRouterWorkerSyncModel,
            lock_timeout=self._lock_timeout,
            heartbeat_trigger=self._heartbeat_trigger,
        )
        self.__fetcher = ServiceRouterWorkerSyncFetcher(
            queue=self._queue,
            queue_desired_minsize=self._queue_desired_minsize,
            min_processing_interval=self._min_processing_interval,
            lock_timeout=self._lock_timeout,
            heartbeater=self.__heartbeater,
        )
        self.__workers = [
            ServiceRouterWorkerSyncWorker(
                queue=self._queue,
                heartbeater=self.__heartbeater,
                pipeline_hinter=pipeline_hinter,
            )
            for _ in range(self._workers_num)
        ]

    @property
    def hint_fetch_model_name(self) -> str:
        return ServiceRouterWorkerSyncModel.__name__

    @property
    def _heartbeater(self) -> Heartbeater[ServiceRouterWorkerSyncPipelineItem]:
        return self.__heartbeater

    @property
    def _fetcher(self) -> Fetcher[ServiceRouterWorkerSyncPipelineItem]:
        return self.__fetcher

    @property
    def _workers(self) -> Sequence["ServiceRouterWorkerSyncWorker"]:
        return self.__workers


class ServiceRouterWorkerSyncFetcher(Fetcher[ServiceRouterWorkerSyncPipelineItem]):
    @sentry_utils.instrument_pipeline_task("ServiceRouterWorkerSyncFetcher.fetch")
    async def fetch(self, limit: int) -> list[ServiceRouterWorkerSyncPipelineItem]:
        sync_lock, _ = get_locker(get_db().dialect_name).get_lockset(
            ServiceRouterWorkerSyncModel.__tablename__
        )
        async with sync_lock:
            async with get_session_ctx() as session:
                now = get_current_datetime()
                res = await session.execute(
                    select(ServiceRouterWorkerSyncModel)
                    .join(RunModel, RunModel.id == ServiceRouterWorkerSyncModel.run_id)
                    .where(
                        RunModel.status == RunStatus.RUNNING,
                        or_(
                            ServiceRouterWorkerSyncModel.last_processed_at
                            <= now - self._min_processing_interval,
                            ServiceRouterWorkerSyncModel.last_processed_at
                            == ServiceRouterWorkerSyncModel.created_at,
                        ),
                        or_(
                            ServiceRouterWorkerSyncModel.lock_expires_at.is_(None),
                            ServiceRouterWorkerSyncModel.lock_expires_at < now,
                        ),
                    )
                    .order_by(ServiceRouterWorkerSyncModel.last_processed_at.asc())
                    .limit(limit)
                    .with_for_update(
                        skip_locked=True, key_share=True, of=ServiceRouterWorkerSyncModel
                    )
                    .options(
                        load_only(
                            ServiceRouterWorkerSyncModel.id,
                            ServiceRouterWorkerSyncModel.run_id,
                            ServiceRouterWorkerSyncModel.lock_token,
                            ServiceRouterWorkerSyncModel.lock_expires_at,
                        )
                    )
                )
                rows = list(res.scalars().all())
                lock_expires_at = get_current_datetime() + self._lock_timeout
                lock_token = uuid.uuid4()
                items: list[ServiceRouterWorkerSyncPipelineItem] = []
                for row in rows:
                    prev_lock_expired = row.lock_expires_at is not None
                    row.lock_expires_at = lock_expires_at
                    row.lock_token = lock_token
                    row.lock_owner = ServiceRouterWorkerSyncPipeline.__name__
                    items.append(
                        ServiceRouterWorkerSyncPipelineItem(
                            __tablename__=ServiceRouterWorkerSyncModel.__tablename__,
                            id=row.id,
                            lock_expires_at=lock_expires_at,
                            lock_token=lock_token,
                            prev_lock_expired=prev_lock_expired,
                            run_id=row.run_id,
                        )
                    )
                await session.commit()
        return items


class _SyncRowUpdateMap(ItemUpdateMap, total=False):
    pass


class ServiceRouterWorkerSyncWorker(Worker[ServiceRouterWorkerSyncPipelineItem]):
    def __init__(
        self,
        queue: asyncio.Queue[ServiceRouterWorkerSyncPipelineItem],
        heartbeater: Heartbeater[ServiceRouterWorkerSyncPipelineItem],
        pipeline_hinter: PipelineHinterProtocol,
    ) -> None:
        super().__init__(
            queue=queue,
            heartbeater=heartbeater,
            pipeline_hinter=pipeline_hinter,
        )

    @sentry_utils.instrument_pipeline_task("ServiceRouterWorkerSyncWorker.process")
    async def process(self, item: ServiceRouterWorkerSyncPipelineItem) -> None:
        async with get_session_ctx() as session:
            res = await session.execute(
                select(ServiceRouterWorkerSyncModel)
                .where(
                    ServiceRouterWorkerSyncModel.id == item.id,
                    ServiceRouterWorkerSyncModel.lock_token == item.lock_token,
                )
                .options(selectinload(ServiceRouterWorkerSyncModel.run))
            )
            sync_row = res.unique().scalar_one_or_none()
            if sync_row is None:
                log_lock_token_mismatch(logger, item)
                return
            run_model = sync_row.run
            if (
                run_model.deleted
                or run_model.status.is_finished()
                or run_model.status != RunStatus.RUNNING
                or not run_model_has_router_replica_group(run_model)
            ):
                await session.delete(sync_row)
                await session.commit()
                return

        async with get_session_ctx() as session:
            res = await session.execute(
                select(RunModel)
                .where(RunModel.id == item.run_id)
                .options(
                    load_only(RunModel.id, RunModel.run_spec),
                    selectinload(
                        RunModel.jobs.and_(
                            JobModel.status == JobStatus.RUNNING,
                            JobModel.registered == true(),
                        )
                    )
                    .load_only(
                        JobModel.id,
                        JobModel.status,
                        JobModel.registered,
                        JobModel.job_spec_data,
                        JobModel.job_provisioning_data,
                        JobModel.job_runtime_data,
                    )
                    .options(
                        joinedload(JobModel.project).load_only(
                            ProjectModel.id, ProjectModel.ssh_private_key
                        ),
                        joinedload(JobModel.instance)
                        .load_only(InstanceModel.id, InstanceModel.remote_connection_info)
                        .joinedload(InstanceModel.project)
                        .load_only(ProjectModel.id, ProjectModel.ssh_private_key),
                    ),
                )
            )
            run_for_sync = res.unique().scalar_one_or_none()

        if run_for_sync is None:
            async with get_session_ctx() as session:
                await session.execute(
                    delete(ServiceRouterWorkerSyncModel).where(
                        ServiceRouterWorkerSyncModel.id == item.id,
                        ServiceRouterWorkerSyncModel.lock_token == item.lock_token,
                    )
                )
                await session.commit()
            return

        await sync_router_workers_for_run_model(run_for_sync)

        update_map: _SyncRowUpdateMap = {}
        set_processed_update_map_fields(update_map)
        set_unlock_update_map_fields(update_map)
        async with get_session_ctx() as session:
            now = get_current_datetime()
            resolve_now_placeholders(update_map, now=now)
            res2 = await session.execute(
                update(ServiceRouterWorkerSyncModel)
                .where(
                    ServiceRouterWorkerSyncModel.id == item.id,
                    ServiceRouterWorkerSyncModel.lock_token == item.lock_token,
                )
                .values(**update_map)
                .returning(ServiceRouterWorkerSyncModel.id)
            )
            if not list(res2.scalars().all()):
                log_lock_token_changed_after_processing(logger, item)
