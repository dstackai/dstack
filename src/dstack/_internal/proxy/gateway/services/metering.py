"""Gateway minute accumulator. Closed data is published only after durable storage."""

import asyncio
import uuid
from collections.abc import Awaitable, Callable, Mapping
from datetime import datetime, timedelta, timezone
from typing import Any

from dstack._internal.proxy.gateway.services.metering_store import MeteringStore
from dstack._internal.proxy.lib.cancellation import await_completion
from dstack._internal.proxy.lib.errors import ProxyError
from dstack._internal.proxy.lib.schemas.usage import (
    TokenUsage,
    UsageAckResponse,
    UsageBatch,
    UsageBatchPage,
    UsageCheckpoint,
    UsageEntry,
    UsageKey,
)
from dstack._internal.proxy.lib.services.usage import (
    VLLM_PROFILE,
    UsageAttempt,
    UsageObserver,
    normalize_usage,
)
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


class Clock:
    def utc_now(self) -> datetime:
        return datetime.now(timezone.utc)


class MeteringCollector(UsageObserver):
    def __init__(
        self,
        store: MeteringStore,
        clock: Clock | None = None,
        profiles: Mapping[str, str] | None = None,
        max_pending: int = 1440,
        max_entries: int = 10000,
    ):
        self.store = store
        self.clock = clock or Clock()
        self.profiles = dict(profiles or {})
        self.max_pending = max_pending
        self.max_entries = max_entries
        self._lock = asyncio.Lock()
        self._state: UsageCheckpoint | None = None
        self._entries: dict[UsageKey, UsageEntry] = {}
        self._published: set[str] = set()
        self._attempts: set[MeteringAttempt] = set()
        self._storage_error: Exception | None = None
        self._clock_error = False
        self._last_time: datetime | None = None
        self._closed = False
        self._pending_bytes = 0
        self._reconfiguring = False

    async def start(self) -> None:
        async with self._lock:
            if self._state is not None:
                return
            if not self.profiles and not self.store.exists():
                return
            saved = await asyncio.to_thread(self.store.load)
            now = self.clock.utc_now()
            self._state = saved or UsageCheckpoint(active_batch=self._new_batch(now))
            self._entries = {entry.key: entry for entry in self._state.active_batch.entries}
            self._published = {batch.batch_id for batch in self._state.pending_batches}
            self._pending_bytes = sum(
                len(b.model_dump_json().encode()) for b in self._state.pending_batches
            )
            self._last_time = self._state.active_batch.interval_start
            await self._rotate(now)
            await self._save(self._snapshot())

    async def configure_profiles(
        self, profiles: Mapping[str, str], persist: Callable[[], Awaitable[None]] | None = None
    ) -> None:
        async with self._lock:
            self._reconfiguring = True
            try:
                if any(profile != VLLM_PROFILE for profile in profiles.values()):
                    raise ProxyError("Unsupported metering profile")
                changed = {
                    key
                    for key in self.profiles.keys() | profiles.keys()
                    if self.profiles.get(key) != profiles.get(key)
                }
                if any(attempt.key.service_id in changed for attempt in self._attempts):
                    raise ProxyError("Drain in-flight requests before changing metering", 409)
                if self._state is not None:
                    if await self._rotate(self.clock.utc_now()):
                        await self._save(self._snapshot())
                    if any(key.service_id in changed for key in self._entries):
                        raise ProxyError("Change metering at a drained minute boundary", 409)
                if persist is not None:
                    await persist()
                self.profiles = dict(profiles)
            finally:
                self._reconfiguring = False
        await self.start()

    def profile_for(self, service_id: str | None) -> str | None:
        return self.profiles.get(service_id) if service_id is not None else None

    def start_attempt(self, key: UsageKey, profile: str) -> UsageAttempt:
        if (
            self._closed
            or self._reconfiguring
            or self._state is None
            or self._storage_error
            or self._clock_error
            or self.profile_for(key.service_id) != profile
            or profile != VLLM_PROFILE
        ):
            raise ProxyError("Usage metering is unavailable", 503)
        keys = set(self._entries) | {attempt.key for attempt in self._attempts} | {key}
        # Headroom covers pending records and already admitted requests, including late finishers.
        estimated_bytes = (
            self._pending_bytes + (len(self._entries) + len(self._attempts) + 1) * 1024 + 512
        )
        if (
            len(keys) > self.max_entries
            or len(self._state.pending_batches) + len(self._attempts) + 1 >= self.max_pending
            or estimated_bytes > self.store.max_bytes
        ):
            raise ProxyError("Usage storage is full; collection is required", 503)
        attempt = MeteringAttempt(self, key, profile)
        self._attempts.add(attempt)
        return attempt

    async def rotate_if_due(self) -> None:
        async with self._lock:
            if self._state is None:
                return
            changed = await self._rotate(self.clock.utc_now())
            if changed or self._storage_error:
                await self._save(self._snapshot())

    async def get_batches(self, limit: int = 100) -> UsageBatchPage:
        if not 1 <= limit <= 100:
            raise ProxyError("Batch limit must be between 1 and 100")
        async with self._lock:
            if self._state is None:
                raise ProxyError("Usage metering is not initialized", 404)
            batches = [b for b in self._state.pending_batches if b.batch_id in self._published]
            return UsageBatchPage(
                batches=batches[:limit],
                has_more=len(batches) > limit,
            ).model_copy(deep=True)

    async def acknowledge(self, batch_ids: list[str]) -> UsageAckResponse:
        async with self._lock:
            if self._state is None:
                raise ProxyError("Usage metering is not initialized", 404)
            ids = set(batch_ids)
            if self._state.active_batch.batch_id in ids:
                raise ProxyError("Cannot acknowledge the active interval")
            if any(
                b.batch_id in ids and b.batch_id not in self._published
                for b in self._state.pending_batches
            ):
                raise ProxyError("Cannot acknowledge an unpublished batch")
            state = self._snapshot()
            candidate = state.model_copy(
                update={
                    "pending_batches": [b for b in state.pending_batches if b.batch_id not in ids]
                }
            )
            await self._save(candidate)
            self._state = candidate
            self._pending_bytes = sum(
                len(b.model_dump_json().encode()) for b in candidate.pending_batches
            )
            return UsageAckResponse(acknowledged_batch_ids=list(dict.fromkeys(batch_ids)))

    async def checkpoint(self) -> None:
        async with self._lock:
            if self._state is not None:
                await self._save(self._snapshot())

    async def close(self) -> None:
        self._closed = True
        try:
            for attempt in list(self._attempts):
                await attempt.finish()
            await self.checkpoint()
        finally:
            self.store.close()

    async def _finish(self, attempt: "MeteringAttempt") -> None:
        async with self._lock:
            if attempt.finished:
                return
            if not attempt.dispatched:
                attempt.finished = True
                self._attempts.discard(attempt)
                return
            try:
                rotated = await self._rotate(self.clock.utc_now())
            except ProxyError:
                # Cannot classify a backward-clock observation into a closed interval.
                # Keep the attempt for reconciliation; do not silently discard it.
                logger.error("Usage finalization paused after a backward clock jump")
                raise
            previous = self._entries.get(attempt.key) or UsageEntry(**attempt.key.model_dump())
            usage = attempt.usage or TokenUsage()
            values = {
                name: getattr(previous, name) + getattr(usage, name)
                for name in TokenUsage.model_fields
            }
            self._entries[attempt.key] = UsageEntry(
                **attempt.key.model_dump(),
                **values,
                unknown_usage_attempts=previous.unknown_usage_attempts
                + int(attempt.usage is None),
            )
            attempt.finished = True
            self._attempts.discard(attempt)
            if rotated:
                try:
                    await self._save(self._snapshot())
                except (OSError, ValueError):
                    logger.exception("Usage retained in memory after checkpoint failure")

    async def _rotate(self, now: datetime) -> bool:
        assert self._state is not None
        if self._last_time is not None and now < self._last_time:
            self._clock_error = True
            raise ProxyError("Usage clock moved backwards; reconciliation is required", 503)
        self._last_time = now
        if now < self._state.active_batch.interval_end:
            return False
        previous = self._state.active_batch.model_copy(
            update={"entries": list(self._entries.values())}
        )
        pending = [*self._state.pending_batches]
        if previous.entries:
            pending.append(previous)
            self._pending_bytes += len(previous.model_dump_json().encode())
        self._state = self._state.model_copy(
            update={"active_batch": self._new_batch(now), "pending_batches": pending}
        )
        self._entries = {}
        return True

    def _snapshot(self) -> UsageCheckpoint:
        assert self._state is not None
        return self._state.model_copy(
            update={
                "active_batch": self._state.active_batch.model_copy(
                    update={"entries": list(self._entries.values())}
                )
            },
            deep=True,
        )

    async def _save(self, state: UsageCheckpoint) -> None:
        try:
            await self.store.save(state)
        except (OSError, ValueError) as exc:
            self._storage_error = exc
            raise
        self._published = {batch.batch_id for batch in state.pending_batches}
        self._storage_error = None

    @staticmethod
    def _new_batch(now: datetime) -> UsageBatch:
        start = now.astimezone(timezone.utc).replace(second=0, microsecond=0)
        return UsageBatch(
            batch_id=uuid.uuid4().hex,
            interval_start=start,
            interval_end=start + timedelta(seconds=60),
        )


class MeteringAttempt(UsageAttempt):
    def __init__(self, collector: MeteringCollector, key: UsageKey, profile: str):
        self.collector = collector
        self.key = key
        self.profile = profile
        self.dispatched = False
        self.upstream_done = False
        self.finished = False
        self.usage: TokenUsage | None = None
        self._finish_task: asyncio.Task[None] | None = None

    def observe_usage(self, usage: Any) -> None:
        confirmed = normalize_usage(usage, self.profile)
        if confirmed is not None:
            self.usage = confirmed

    def mark_dispatched(self) -> None:
        self.dispatched = True

    def mark_upstream_done(self) -> None:
        self.upstream_done = True

    async def finish(self) -> None:
        if self._finish_task is None:
            self._finish_task = asyncio.create_task(self.collector._finish(self))
        await await_completion(self._finish_task)
