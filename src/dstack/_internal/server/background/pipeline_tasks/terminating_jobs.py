import asyncio
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, Sequence

from sqlalchemy import or_, select
from sqlalchemy.orm import load_only

from dstack._internal.core.models.runs import JobStatus
from dstack._internal.server.background.pipeline_tasks.base import (
    Fetcher,
    Heartbeater,
    Pipeline,
    PipelineItem,
    Worker,
)
from dstack._internal.server.db import get_db, get_session_ctx
from dstack._internal.server.models import JobModel
from dstack._internal.server.services.locking import get_locker
from dstack._internal.server.utils import sentry_utils
from dstack._internal.utils.common import get_current_datetime


@dataclass
class JobTerminatingPipelineItem(PipelineItem):
    volumes_detached_at: Optional[datetime]


class JobTerminatingPipeline(Pipeline[JobTerminatingPipelineItem]):
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
                    .with_for_update(skip_locked=True, key_share=True)
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
        raise NotImplementedError("JobTerminatingWorker.process is not implemented yet")
