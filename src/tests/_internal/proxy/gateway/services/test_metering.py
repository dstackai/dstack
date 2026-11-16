import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from dstack._internal.proxy.gateway.services.metering import Clock, MeteringCollector
from dstack._internal.proxy.gateway.services.metering_store import MeteringStore
from dstack._internal.proxy.lib.errors import ProxyError
from dstack._internal.proxy.lib.schemas.usage import UsageKey
from dstack._internal.proxy.lib.services.usage import VLLM_PROFILE


class FakeClock(Clock):
    def __init__(self):
        self.now = datetime(2026, 11, 16, 10, tzinfo=timezone.utc)

    def utc_now(self):
        return self.now

    def advance(self, seconds=60):
        self.now += timedelta(seconds=seconds)


class FailingStore(MeteringStore):
    fail = False

    async def save(self, state):
        if self.fail:
            raise OSError("injected disk failure")
        await super().save(state)


async def record(collector, user="u", service="s", usage=None):
    attempt = collector.start_attempt(
        UsageKey(consumer_subject_id=user, service_id=service), VLLM_PROFILE
    )
    attempt.mark_dispatched()
    attempt.observe_usage(
        usage
        or dict(
            prompt_tokens=20,
            completion_tokens=3,
            total_tokens=23,
            prompt_tokens_details={"cached_tokens": 5},
        )
    )
    await attempt.finish()
    return attempt


@pytest.mark.asyncio
class TestMeteringCollector:
    async def test_ack_does_not_clear_active(self, tmp_path):
        clock = FakeClock()
        collector = MeteringCollector(
            MeteringStore(tmp_path / "usage.json"), clock=clock, profiles={"s": VLLM_PROFILE}
        )
        await collector.start()
        await record(collector)
        assert not (await collector.get_batches()).batches
        clock.advance()
        await collector.rotate_if_due()
        a = (await collector.get_batches()).batches[0]
        await record(collector)
        await collector.acknowledge([a.batch_id])
        clock.advance()
        await collector.rotate_if_due()
        b = (await collector.get_batches()).batches[0]
        await collector.acknowledge([a.batch_id])
        assert (await collector.get_batches()).batches == [b]
        assert b.entries[0].total_tokens == 23
        assert b.batch_id != a.batch_id
        await collector.close()

    async def test_ack_preserves_other_pending(self, tmp_path):
        clock = FakeClock()
        c = MeteringCollector(
            MeteringStore(tmp_path / "usage.json"), clock=clock, profiles={"s": VLLM_PROFILE}
        )
        await c.start()
        for _ in range(2):
            await record(c)
            clock.advance()
            await c.rotate_if_due()
        p, q = (await c.get_batches()).batches
        await record(c)
        await c.acknowledge([p.batch_id])
        assert (await c.get_batches()).batches == [q]
        clock.advance()
        await c.rotate_if_due()
        assert [b.entries[0].total_tokens for b in (await c.get_batches()).batches] == [23, 23]
        await c.close()

    async def test_rotation_not_published_before_save(self, tmp_path):
        clock = FakeClock()
        store = FailingStore(tmp_path / "usage.json")
        c = MeteringCollector(store, clock=clock, profiles={"s": VLLM_PROFILE})
        await c.start()
        late = await record(c)
        store.fail = True
        clock.advance()
        with pytest.raises(OSError):
            await c.rotate_if_due()
        assert not (await c.get_batches()).batches
        with pytest.raises(ProxyError):
            c.start_attempt(UsageKey(consumer_subject_id="u", service_id="s"), VLLM_PROFILE)
        store.fail = False
        await c.checkpoint()
        assert (await c.get_batches()).batches[0].entries[0].total_tokens == 23
        await late.finish()
        await c.close()

    async def test_failed_ack_is_not_success(self, tmp_path):
        clock = FakeClock()
        store = FailingStore(tmp_path / "usage.json")
        c = MeteringCollector(store, clock=clock, profiles={"s": VLLM_PROFILE})
        await c.start()
        await record(c)
        clock.advance()
        await c.rotate_if_due()
        before = await c.get_batches()
        store.fail = True
        with pytest.raises(OSError):
            await c.acknowledge([before.batches[0].batch_id])
        assert await c.get_batches() == before
        store.fail = False
        await c.acknowledge([before.batches[0].batch_id])
        await c.checkpoint()
        await c.close()
        restored = MeteringCollector(MeteringStore(tmp_path / "usage.json"), clock=clock)
        await restored.start()
        assert not (await restored.get_batches()).batches
        await restored.close()

    async def test_late_finish_and_repeated_cleanup_count_once(self, tmp_path):
        clock = FakeClock()
        c = MeteringCollector(
            MeteringStore(tmp_path / "usage.json"), clock=clock, profiles={"s": VLLM_PROFILE}
        )
        await c.start()
        a = c.start_attempt(UsageKey(consumer_subject_id="u", service_id="s"), VLLM_PROFILE)
        a.mark_dispatched()
        a.observe_usage(dict(prompt_tokens=20, completion_tokens=3, total_tokens=23))
        clock.advance(130)
        await asyncio.gather(a.finish(), a.finish())
        clock.advance(60)
        await c.rotate_if_due()
        batches = (await c.get_batches()).batches
        assert len(batches) == 1
        assert batches[0].interval_start.minute == 2
        assert batches[0].entries[0].total_tokens == 23
        assert batches[0].interval_end - batches[0].interval_start == timedelta(seconds=60)
        await c.close()

    async def test_unknown_only_after_dispatch(self, tmp_path):
        clock = FakeClock()
        c = MeteringCollector(
            MeteringStore(tmp_path / "usage.json"), clock=clock, profiles={"s": VLLM_PROFILE}
        )
        await c.start()
        key = UsageKey(consumer_subject_id="u", service_id="s")
        a = c.start_attempt(key, VLLM_PROFILE)
        await a.finish()
        b = c.start_attempt(key, VLLM_PROFILE)
        b.mark_dispatched()
        await b.finish()
        await b.finish()
        clock.advance()
        await c.rotate_if_due()
        entry = (await c.get_batches()).batches[0].entries[0]
        assert entry.unknown_usage_attempts == 1
        assert entry.total_tokens == 0
        await c.close()

    async def test_backward_clock_pauses_admission(self, tmp_path):
        clock = FakeClock()
        c = MeteringCollector(
            MeteringStore(tmp_path / "usage.json"), clock=clock, profiles={"s": VLLM_PROFILE}
        )
        await c.start()
        await record(c)
        clock.advance(-1)
        with pytest.raises(ProxyError):
            await c.rotate_if_due()
        with pytest.raises(ProxyError):
            c.start_attempt(UsageKey(consumer_subject_id="u", service_id="s"), VLLM_PROFILE)
        await c.close()

    async def test_active_ack_rejected_atomically(self, tmp_path):
        clock = FakeClock()
        store = MeteringStore(tmp_path / "usage.json")
        c = MeteringCollector(store, clock=clock, profiles={"s": VLLM_PROFILE})
        await c.start()
        await record(c)
        clock.advance()
        await c.rotate_if_due()
        before = await c.get_batches()
        state = store.load()
        assert state is not None
        with pytest.raises(ProxyError):
            await c.acknowledge([before.batches[0].batch_id, state.active_batch.batch_id])
        assert await c.get_batches() == before
        await c.close()

    async def test_concurrent_finalizers_and_storage_backpressure(self, tmp_path):
        clock = FakeClock()
        c = MeteringCollector(
            MeteringStore(tmp_path / "usage.json"),
            clock=clock,
            profiles={"s": VLLM_PROFILE},
            max_pending=32,
            max_entries=1,
        )
        await c.start()
        await asyncio.gather(*(record(c) for _ in range(20)))
        with pytest.raises(ProxyError):
            c.start_attempt(
                UsageKey(consumer_subject_id="different", service_id="s"), VLLM_PROFILE
            )
        clock.advance()
        await c.rotate_if_due()
        entry = (await c.get_batches()).batches[0].entries[0]
        assert (
            entry.prompt_tokens,
            entry.cached_prompt_tokens,
            entry.completion_tokens,
            entry.total_tokens,
        ) == (400, 100, 60, 460)
        await c.close()

    async def test_old_checkpoint_cannot_resurrect_acked_batch(self, tmp_path):
        clock = FakeClock()
        path = tmp_path / "usage.json"
        c = MeteringCollector(MeteringStore(path), clock=clock, profiles={"s": VLLM_PROFILE})
        await c.start()
        await record(c)
        clock.advance()
        await c.rotate_if_due()
        batch = (await c.get_batches()).batches[0]
        await asyncio.gather(c.checkpoint(), c.acknowledge([batch.batch_id]), c.checkpoint())
        await c.close()
        c = MeteringCollector(MeteringStore(path), clock=clock)
        await c.start()
        assert not (await c.get_batches()).batches
        await c.close()


@pytest.mark.asyncio
async def test_repeated_cancellation_does_not_abandon_finalization(tmp_path):
    clock = FakeClock()
    collector = MeteringCollector(
        MeteringStore(tmp_path / "usage.json"), clock=clock, profiles={"s": VLLM_PROFILE}
    )
    await collector.start()
    attempt = collector.start_attempt(
        UsageKey(consumer_subject_id="u", service_id="s"), VLLM_PROFILE
    )
    attempt.mark_dispatched()
    attempt.observe_usage(dict(prompt_tokens=20, completion_tokens=3, total_tokens=23))
    await collector._lock.acquire()
    task = asyncio.create_task(attempt.finish())
    try:
        for _ in range(3):
            await asyncio.sleep(0)
            task.cancel()
            await asyncio.sleep(0)
    finally:
        collector._lock.release()
    with pytest.raises(asyncio.CancelledError):
        await task
    # Finalized before cleanup returns, not postponed until process shutdown.
    clock.advance()
    await collector.rotate_if_due()
    page = await collector.get_batches()
    await collector.close()
    assert len(page.batches) == 1 and page.batches[0].entries[0].completion_tokens == 3
