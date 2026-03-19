import asyncio
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Sequence

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import load_only

from dstack._internal.core.models.runs import RunStatus
from dstack._internal.server.background.pipeline_tasks.base import (
    Fetcher,
    Heartbeater,
    Pipeline,
    PipelineItem,
    Worker,
)
from dstack._internal.server.db import get_db, get_session_ctx
from dstack._internal.server.models import RunModel
from dstack._internal.server.services.locking import get_locker
from dstack._internal.server.utils import sentry_utils
from dstack._internal.utils.common import get_current_datetime


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
        return None
