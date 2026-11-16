import asyncio
import threading
from datetime import datetime, timedelta, timezone

import pytest

from dstack._internal.proxy.gateway.services.metering_store import MeteringStore
from dstack._internal.proxy.lib.schemas.usage import UsageBatch, UsageCheckpoint


def checkpoint():
    start = datetime(2026, 11, 16, 10, tzinfo=timezone.utc)
    return UsageCheckpoint(
        collector_id="collector",
        active_batch=UsageBatch(
            batch_id="a", interval_start=start, interval_end=start + timedelta(seconds=60)
        ),
    )


@pytest.mark.asyncio
class TestMeteringStore:
    async def test_roundtrip_and_missing_initialized_state(self, tmp_path):
        path = tmp_path / "usage.json"
        store = MeteringStore(path)
        assert store.load() is None
        await store.save(checkpoint())
        assert store.load() == checkpoint()
        path.unlink()
        with pytest.raises(ValueError, match="missing"):
            store.load()
        store.close()

    async def test_corruption_is_not_a_fresh_collector(self, tmp_path):
        path = tmp_path / "usage.json"
        path.write_text('{"broken":')
        store = MeteringStore(path)
        with pytest.raises(ValueError):
            store.load()
        store.close()

    async def test_failed_replace_preserves_previous_checkpoint(self, tmp_path, monkeypatch):
        path = tmp_path / "usage.json"
        store = MeteringStore(path)
        await store.save(checkpoint())
        original = path.read_bytes()

        def fail(*args):
            raise OSError("replace failed")

        monkeypatch.setattr(
            "dstack._internal.proxy.gateway.services.metering_store.os.replace", fail
        )
        with pytest.raises(OSError):
            await store.save(checkpoint())
        assert path.read_bytes() == original
        assert not list(tmp_path.glob("*.tmp"))
        store.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel_count", [1, 2, 3])
async def test_cancelled_save_finishes_before_next_writer(tmp_path, monkeypatch, cancel_count):
    store = MeteringStore(tmp_path / "usage.json")
    entered = threading.Event()
    release = threading.Event()
    original = store._save
    order = []

    def delayed(state):
        if state.active_batch.batch_id == "a":
            entered.set()
            release.wait(timeout=5)
        original(state)
        order.append(state.active_batch.batch_id)

    monkeypatch.setattr(store, "_save", delayed)
    first = asyncio.create_task(store.save(checkpoint()))
    await asyncio.to_thread(entered.wait, 5)
    for _ in range(cancel_count):
        first.cancel()
        await asyncio.sleep(0)
        await asyncio.sleep(0)
    other = checkpoint().model_copy(
        update={"active_batch": checkpoint().active_batch.model_copy(update={"batch_id": "b"})}
    )
    second = asyncio.create_task(store.save(other))
    # Task scheduling barriers, not timing assumptions about disk latency.
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    retained_ownership = not first.done()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await first
    await second
    assert retained_ownership, "cancelled writer must retain ownership until its thread completes"
    assert order == ["a", "b"]
    saved = store.load()
    assert saved is not None
    assert saved.active_batch.batch_id == "b"
    store.close()
