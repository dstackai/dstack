import asyncio
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Sequence

from sqlalchemy import or_, select
from sqlalchemy.orm import load_only

from dstack._internal.core.models.runs import JobStatus, RunStatus
from dstack._internal.server.background.pipeline_tasks.base import (
    Fetcher,
    Heartbeater,
    Pipeline,
    PipelineItem,
    Worker,
)
from dstack._internal.server.db import get_db, get_session_ctx
from dstack._internal.server.models import JobModel, RunModel
from dstack._internal.server.services.locking import get_locker
from dstack._internal.server.utils import sentry_utils
from dstack._internal.utils.common import get_current_datetime
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class JobRunningPipelineItem(PipelineItem):
    status: JobStatus


class JobRunningPipeline(Pipeline[JobRunningPipelineItem]):
    def __init__(
        self,
        workers_num: int = 10,
        queue_lower_limit_factor: float = 0.5,
        queue_upper_limit_factor: float = 2.0,
        min_processing_interval: timedelta = timedelta(seconds=10),
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
        self.__heartbeater = Heartbeater[JobRunningPipelineItem](
            model_type=JobModel,
            lock_timeout=self._lock_timeout,
            heartbeat_trigger=self._heartbeat_trigger,
        )
        self.__fetcher = JobRunningFetcher(
            queue=self._queue,
            queue_desired_minsize=self._queue_desired_minsize,
            min_processing_interval=self._min_processing_interval,
            lock_timeout=self._lock_timeout,
            heartbeater=self._heartbeater,
        )
        self.__workers = [
            JobRunningWorker(queue=self._queue, heartbeater=self._heartbeater)
            for _ in range(self._workers_num)
        ]

    @property
    def hint_fetch_model_name(self) -> str:
        return JobModel.__name__

    @property
    def _heartbeater(self) -> Heartbeater[JobRunningPipelineItem]:
        return self.__heartbeater

    @property
    def _fetcher(self) -> Fetcher[JobRunningPipelineItem]:
        return self.__fetcher

    @property
    def _workers(self) -> Sequence["JobRunningWorker"]:
        return self.__workers


class JobRunningFetcher(Fetcher[JobRunningPipelineItem]):
    def __init__(
        self,
        queue: asyncio.Queue[JobRunningPipelineItem],
        queue_desired_minsize: int,
        min_processing_interval: timedelta,
        lock_timeout: timedelta,
        heartbeater: Heartbeater[JobRunningPipelineItem],
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

    @sentry_utils.instrument_named_task("pipeline_tasks.JobRunningFetcher.fetch")
    async def fetch(self, limit: int) -> list[JobRunningPipelineItem]:
        job_lock, _ = get_locker(get_db().dialect_name).get_lockset(JobModel.__tablename__)
        async with job_lock:
            async with get_session_ctx() as session:
                now = get_current_datetime()
                res = await session.execute(
                    select(JobModel)
                    .join(JobModel.run)
                    .where(
                        JobModel.status.in_(
                            [JobStatus.PROVISIONING, JobStatus.PULLING, JobStatus.RUNNING]
                        ),
                        RunModel.status.not_in([RunStatus.TERMINATING]),
                        JobModel.last_processed_at < now - self._min_processing_interval,
                        or_(
                            JobModel.lock_expires_at.is_(None),
                            JobModel.lock_expires_at < now,
                        ),
                        or_(
                            JobModel.lock_owner.is_(None),
                            JobModel.lock_owner == JobRunningPipeline.__name__,
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
                            JobModel.status,
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
                    job_model.lock_owner = JobRunningPipeline.__name__
                    items.append(
                        JobRunningPipelineItem(
                            __tablename__=JobModel.__tablename__,
                            id=job_model.id,
                            lock_expires_at=lock_expires_at,
                            lock_token=lock_token,
                            prev_lock_expired=prev_lock_expired,
                            status=job_model.status,
                        )
                    )
                await session.commit()
        return items


class JobRunningWorker(Worker[JobRunningPipelineItem]):
    def __init__(
        self,
        queue: asyncio.Queue[JobRunningPipelineItem],
        heartbeater: Heartbeater[JobRunningPipelineItem],
    ) -> None:
        super().__init__(
            queue=queue,
            heartbeater=heartbeater,
        )

    @sentry_utils.instrument_named_task("pipeline_tasks.JobRunningWorker.process")
    async def process(self, item: JobRunningPipelineItem):
        raise NotImplementedError("JobRunningWorker.process() is implemented in a later step")
