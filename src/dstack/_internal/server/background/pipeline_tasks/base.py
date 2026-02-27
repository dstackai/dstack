import asyncio
import math
import random
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import (
    Any,
    ClassVar,
    Final,
    Generic,
    Optional,
    Protocol,
    Sequence,
    TypedDict,
    TypeVar,
    Union,
)

from sqlalchemy import and_, or_, update
from sqlalchemy.orm import Mapped

from dstack._internal.server.db import get_session_ctx
from dstack._internal.utils.common import get_current_datetime
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class PipelineItem:
    """
    Pipelines can work with this class or its subclass if the worker needs to access extra attributes.
    """

    __tablename__: str
    id: uuid.UUID
    lock_expires_at: datetime
    lock_token: uuid.UUID
    prev_lock_expired: bool


ItemT = TypeVar("ItemT", bound=PipelineItem)


class PipelineModel(Protocol):
    """
    Heartbeater can work with any DB model implementing this protocol.
    """

    __tablename__: str
    __mapper__: ClassVar[Any]
    __table__: ClassVar[Any]
    id: Mapped[uuid.UUID]
    lock_expires_at: Mapped[Optional[datetime]]
    lock_token: Mapped[Optional[uuid.UUID]]


class PipelineError(Exception):
    pass


class Pipeline(Generic[ItemT], ABC):
    def __init__(
        self,
        workers_num: int,
        queue_lower_limit_factor: float,
        queue_upper_limit_factor: float,
        min_processing_interval: timedelta,
        lock_timeout: timedelta,
        heartbeat_trigger: timedelta,
    ) -> None:
        self._workers_num = workers_num
        self._queue_lower_limit_factor = queue_lower_limit_factor
        self._queue_upper_limit_factor = queue_upper_limit_factor
        self._queue_desired_minsize = math.ceil(workers_num * queue_lower_limit_factor)
        self._queue_maxsize = math.ceil(workers_num * queue_upper_limit_factor)
        self._min_processing_interval = min_processing_interval
        self._lock_timeout = lock_timeout
        self._heartbeat_trigger = heartbeat_trigger
        self._queue = asyncio.Queue[ItemT](maxsize=self._queue_maxsize)
        self._tasks: list[asyncio.Task] = []
        self._running = False
        self._shutdown = False

    def start(self):
        """
        Starts all pipeline tasks.
        """
        if self._running:
            return
        if self._shutdown:
            raise PipelineError("Cannot start pipeline after shutdown.")
        self._running = True
        self._tasks.append(asyncio.create_task(self._heartbeater.start()))
        for worker in self._workers:
            self._tasks.append(asyncio.create_task(worker.start()))
        self._tasks.append(asyncio.create_task(self._fetcher.start()))

    def shutdown(self):
        """
        Stops the pipeline from processing new items and signals running tasks to cancel.
        """
        if self._shutdown:
            return
        self._shutdown = True
        self._running = False
        self._fetcher.stop()
        for worker in self._workers:
            worker.stop()
        self._heartbeater.stop()
        for task in self._tasks:
            if not task.done():
                task.cancel()

    async def drain(self):
        """
        Waits for all pipeline tasks to finish cleanup after shutdown.
        """
        if not self._shutdown:
            raise PipelineError("Cannot drain running pipeline. Call `shutdown()` first.")
        results = await asyncio.gather(*self._tasks, return_exceptions=True)
        for task, result in zip(self._tasks, results):
            if isinstance(result, BaseException) and not isinstance(
                result, asyncio.CancelledError
            ):
                logger.error(
                    "Unexpected exception when draining pipeline task %r",
                    task,
                    exc_info=(type(result), result, result.__traceback__),
                )

    def hint_fetch(self):
        self._fetcher.hint()

    @property
    @abstractmethod
    def hint_fetch_model_name(self) -> str:
        pass

    @property
    @abstractmethod
    def _heartbeater(self) -> "Heartbeater[ItemT]":
        pass

    @property
    @abstractmethod
    def _fetcher(self) -> "Fetcher[ItemT]":
        pass

    @property
    @abstractmethod
    def _workers(self) -> Sequence["Worker[ItemT]"]:
        pass


class Heartbeater(Generic[ItemT]):
    def __init__(
        self,
        model_type: type[PipelineModel],
        lock_timeout: timedelta,
        heartbeat_trigger: timedelta,
        heartbeat_delay: float = 1.0,
    ) -> None:
        self._model_type = model_type
        self._lock_timeout = lock_timeout
        self._hearbeat_margin = heartbeat_trigger
        self._items: dict[uuid.UUID, ItemT] = {}
        self._untrack_lock = asyncio.Lock()
        self._heartbeat_delay = heartbeat_delay
        self._running = False

    async def start(self):
        self._running = True
        while self._running:
            try:
                await self.heartbeat()
            except Exception:
                logger.exception("Unexpected exception when running heartbeat")
            await asyncio.sleep(self._heartbeat_delay)

    def stop(self):
        self._running = False

    async def track(self, item: ItemT):
        self._items[item.id] = item

    async def untrack(self, item: ItemT):
        async with self._untrack_lock:
            tracked = self._items.get(item.id)
            # Prevent expired fetch iteration to unlock item processed by new iteration.
            if tracked is not None and tracked.lock_token == item.lock_token:
                del self._items[item.id]

    async def heartbeat(self):
        items_to_update: list[ItemT] = []
        now = get_current_datetime()
        items = list(self._items.values())
        failed_to_heartbeat_count = 0
        for item in items:
            if item.lock_expires_at < now:
                failed_to_heartbeat_count += 1
                await self.untrack(item)
            elif item.lock_expires_at < now + self._hearbeat_margin:
                items_to_update.append(item)
        if failed_to_heartbeat_count > 0:
            logger.warning(
                "Failed to heartbeat %d %s items in time."
                " The items are expected to be processed on another fetch iteration.",
                failed_to_heartbeat_count,
                self._model_type.__tablename__,
            )
        if len(items_to_update) == 0:
            return
        logger.debug(
            "Updating lock_expires_at for items: %s", [str(r.id) for r in items_to_update]
        )
        async with get_session_ctx() as session:
            per_item_filters = [
                and_(
                    self._model_type.id == item.id, self._model_type.lock_token == item.lock_token
                )
                for item in items_to_update
            ]
            res = await session.execute(
                update(self._model_type)
                .where(or_(*per_item_filters))
                .values(lock_expires_at=now + self._lock_timeout)
                .returning(self._model_type.id)
            )
            updated_ids = set(res.scalars().all())
        failed_to_update_count = 0
        for item in items_to_update:
            if item.id in updated_ids:
                item.lock_expires_at = now + self._lock_timeout
            else:
                failed_to_update_count += 1
                await self.untrack(item)
        if failed_to_update_count > 0:
            logger.warning(
                "Failed to update %s lock_expires_at of %d items: lock_token changed."
                " The items are expected to be processed and updated on another fetch iteration.",
                self._model_type.__tablename__,
                failed_to_update_count,
            )


class Fetcher(Generic[ItemT], ABC):
    _DEFAULT_FETCH_DELAYS = [0.5, 1, 2, 5]

    def __init__(
        self,
        queue: asyncio.Queue[ItemT],
        queue_desired_minsize: int,
        min_processing_interval: timedelta,
        lock_timeout: timedelta,
        heartbeater: Heartbeater[ItemT],
        queue_check_delay: float = 1.0,
        fetch_delays: Optional[list[float]] = None,
    ) -> None:
        self._queue = queue
        self._queue_desired_minsize = queue_desired_minsize
        self._min_processing_interval = min_processing_interval
        self._lock_timeout = lock_timeout
        self._heartbeater = heartbeater
        self._queue_check_delay = queue_check_delay
        if fetch_delays is None:
            fetch_delays = self._DEFAULT_FETCH_DELAYS
        self._fetch_delays = fetch_delays
        self._running = False
        self._fetch_event = asyncio.Event()

    async def start(self):
        self._running = True
        empty_fetch_count = 0
        while self._running:
            if self._queue.qsize() >= self._queue_desired_minsize:
                await asyncio.sleep(self._queue_check_delay)
                continue
            fetch_limit = self._queue.maxsize - self._queue.qsize()
            try:
                items = await self.fetch(limit=fetch_limit)
            except Exception:
                logger.exception("Unexpected exception when fetching new items")
                items = []
            if len(items) == 0:
                try:
                    await asyncio.wait_for(
                        self._fetch_event.wait(),
                        timeout=self._next_fetch_delay(empty_fetch_count),
                    )
                except TimeoutError:
                    pass
                empty_fetch_count += 1
                self._fetch_event.clear()
                continue
            else:
                empty_fetch_count = 0
            for item in items:
                self._queue.put_nowait(item)  # should never raise
                await self._heartbeater.track(item)

    def stop(self):
        self._running = False

    def hint(self):
        self._fetch_event.set()

    @abstractmethod
    async def fetch(self, limit: int) -> list[ItemT]:
        pass

    def _next_fetch_delay(self, empty_fetch_count: int) -> float:
        next_delay = self._fetch_delays[min(empty_fetch_count, len(self._fetch_delays) - 1)]
        jitter = random.random() * 0.4 - 0.2
        return next_delay * (1 + jitter)


class Worker(Generic[ItemT], ABC):
    def __init__(
        self,
        queue: asyncio.Queue[ItemT],
        heartbeater: Heartbeater[ItemT],
    ) -> None:
        self._queue = queue
        self._heartbeater = heartbeater
        self._running = False

    async def start(self):
        self._running = True
        while self._running:
            item = await self._queue.get()
            logger.debug("Processing %s item %s", item.__tablename__, item.id)
            try:
                await self.process(item)
            except Exception:
                logger.exception("Unexpected exception when processing item")
            finally:
                await self._heartbeater.untrack(item)
            logger.debug("Processed %s item %s", item.__tablename__, item.id)

    def stop(self):
        self._running = False

    @abstractmethod
    async def process(self, item: ItemT):
        pass


class _NowPlaceholder:
    pass


NOW_PLACEHOLDER: Final = _NowPlaceholder()

# Timestamp value stored in update maps before being resolved to current time.
UpdateMapDateTime = Union[datetime, _NowPlaceholder]


class UnlockUpdateMap(TypedDict, total=False):
    lock_expires_at: Optional[datetime]
    lock_token: Optional[uuid.UUID]
    lock_owner: Optional[str]


class ProcessedUpdateMap(TypedDict, total=False):
    last_processed_at: UpdateMapDateTime


class ItemUpdateMap(UnlockUpdateMap, ProcessedUpdateMap, total=False):
    lock_expires_at: Optional[datetime]
    lock_token: Optional[uuid.UUID]
    lock_owner: Optional[str]
    last_processed_at: UpdateMapDateTime


def set_unlock_update_map_fields(update_map: UnlockUpdateMap):
    update_map["lock_expires_at"] = None
    update_map["lock_token"] = None
    update_map["lock_owner"] = None


def set_processed_update_map_fields(
    update_map: ProcessedUpdateMap,
    now: UpdateMapDateTime = NOW_PLACEHOLDER,
):
    update_map["last_processed_at"] = now


def resolve_now_placeholders(update_values: Any, now: datetime):
    if isinstance(update_values, list):
        for update_row in update_values:
            resolve_now_placeholders(update_row, now)
        return
    for key, value in update_values.items():
        if value is NOW_PLACEHOLDER:
            update_values[key] = now
