import asyncio
import math
import random
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Any, ClassVar, Generic, Optional, Protocol, Sequence, TypeVar

from sqlalchemy import and_, or_, update
from sqlalchemy.orm import Mapped

from dstack._internal.server.db import get_session_ctx
from dstack._internal.utils.common import get_current_datetime
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


class PipelineItem(Protocol):
    id: uuid.UUID
    lock_expires_at: datetime
    lock_token: uuid.UUID


class PipelineModel(Protocol):
    id: Mapped[uuid.UUID]
    lock_expires_at: Mapped[Optional[datetime]]
    lock_token: Mapped[Optional[uuid.UUID]]

    __mapper__: ClassVar[Any]
    __table__: ClassVar[Any]


class Pipeline(ABC):
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
        self._queue = asyncio.Queue[PipelineItem](maxsize=self._queue_maxsize)

    def start(self):
        asyncio.create_task(self._heartbeater.start())
        for worker in self._workers:
            asyncio.create_task(worker.start())
        asyncio.create_task(self._fetcher.start())

    def shutdown(self):
        self._fetcher.shutdown()
        self._heartbeater.shutdown()

    def hint_fetch(self):
        self._fetcher.hint()

    @property
    @abstractmethod
    def hint_fetch_model_name(self) -> str:
        pass

    @property
    @abstractmethod
    def _heartbeater(self) -> "Heartbeater":
        pass

    @property
    @abstractmethod
    def _fetcher(self) -> "Fetcher":
        pass

    @property
    @abstractmethod
    def _workers(self) -> Sequence["Worker"]:
        pass


ModelT = TypeVar("ModelT", bound=PipelineModel)


class Heartbeater(Generic[ModelT]):
    def __init__(
        self,
        model_type: type[ModelT],
        lock_timeout: timedelta,
        heartbeat_trigger: timedelta,
        heartbeat_delay: float = 1.0,
    ) -> None:
        self._model_type = model_type
        self._lock_timeout = lock_timeout
        self._hearbeat_margin = heartbeat_trigger
        self._items: dict[uuid.UUID, PipelineItem] = {}
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

    def shutdown(self):
        self._running = False

    async def track(self, item: PipelineItem):
        self._items[item.id] = item

    async def untrack(self, item: PipelineItem):
        async with self._untrack_lock:
            tracked = self._items.get(item.id)
            # Prevent expired fetch iteration to unlock item processed by new iteration.
            if tracked is not None and tracked.lock_token == item.lock_token:
                del self._items[item.id]

    async def heartbeat(self):
        updated_items: list[PipelineItem] = []
        now = get_current_datetime()
        items = list(self._items.values())
        for item in items:
            if item.lock_expires_at < now:
                logger.warning(
                    "Failed to heartbeat item %s in time."
                    " The item is expected to be processed on another fetch iteration.",
                    item.id,
                )
                await self.untrack(item)
            elif item.lock_expires_at < now + self._hearbeat_margin:
                updated_items.append(item)
        if len(updated_items) == 0:
            return
        logger.debug("Updating lock_expires_at for items: %s", [str(r.id) for r in updated_items])
        async with get_session_ctx() as session:
            per_item_filters = [
                and_(
                    self._model_type.id == item.id, self._model_type.lock_token == item.lock_token
                )
                for item in updated_items
            ]
            res = await session.execute(
                update(self._model_type)
                .where(or_(*per_item_filters))
                .values(lock_expires_at=now + self._lock_timeout)
            )
            if res.rowcount == 0:  # pyright: ignore[reportAttributeAccessIssue]
                logger.warning(
                    "Failed to update lock_expires_at: lock_token changed."
                    " The item is expected to be processed and updated on another fetch iteration."
                )
                return
        for item in updated_items:
            item.lock_expires_at = now + self._lock_timeout


class Fetcher(ABC):
    _DEFAULT_FETCH_DELAYS = [0.5, 1, 2, 5]

    def __init__(
        self,
        queue: asyncio.Queue[PipelineItem],
        queue_desired_minsize: int,
        min_processing_interval: timedelta,
        lock_timeout: timedelta,
        heartbeater: Heartbeater,
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

    def shutdown(self):
        self._running = False

    def hint(self):
        self._fetch_event.set()

    @abstractmethod
    async def fetch(self, limit: int) -> list[PipelineItem]:
        pass

    def _next_fetch_delay(self, empty_fetch_count: int) -> float:
        next_delay = self._fetch_delays[min(empty_fetch_count, len(self._fetch_delays) - 1)]
        jitter = random.random() * 0.4 - 0.2
        return next_delay * (1 + jitter)


class Worker(ABC):
    def __init__(
        self,
        queue: asyncio.Queue[PipelineItem],
        heartbeater: Heartbeater,
    ) -> None:
        self._queue = queue
        self._heartbeater = heartbeater

    async def start(self):
        while True:
            item = await self._queue.get()
            try:
                await self.process(item)
            except Exception:
                logger.exception("Unexpected exception when processing item")
            await self._heartbeater.untrack(item)

    @abstractmethod
    async def process(self, item: PipelineItem):
        pass
