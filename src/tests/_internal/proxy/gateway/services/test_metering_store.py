import asyncio
import json
import threading
from datetime import datetime, timedelta, timezone

import pytest

from dstack._internal.proxy.gateway.services.metering_store import MeteringStore
from dstack._internal.proxy.lib.schemas.usage import UsageBatch, UsageCheckpoint


def checkpoint():
    start = datetime(2026, 11, 16, 10, tzinfo=timezone.utc)
    return UsageCheckpoint(
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


@pytest.mark.asyncio
async def test_v1_conversion_preserves_all_batches_and_survives_marker_failure(
    tmp_path, monkeypatch
):
    path = tmp_path / "usage.json"
    marker = path.with_suffix(".json.initialized")
    data = checkpoint().model_dump(mode="json")
    old_batch = dict(
        data["active_batch"],
        batch_id="pending",
        interval_start="2026-11-16T09:59:00Z",
        interval_end="2026-11-16T10:00:00Z",
        entries=[
            dict(
                consumer_subject_id="u",
                service_id="s",
                prompt_tokens=20,
                cached_prompt_tokens=5,
                completion_tokens=3,
                total_tokens=23,
                unknown_usage_attempts=0,
            )
        ],
    )
    data.update(schema_version=1, collector_id="a" * 32, pending_batches=[old_batch])
    path.write_text(json.dumps(data))
    marker.write_text("a" * 32)
    store = MeteringStore(path)
    original = store._atomic_write

    def fail_marker(target, content):
        if target == marker:
            raise OSError("marker write interrupted")
        original(target, content)

    monkeypatch.setattr(store, "_atomic_write", fail_marker)
    try:
        with pytest.raises(OSError, match="interrupted"):
            store.load()
        saved = json.loads(path.read_text())
        assert saved["schema_version"] == 2 and "collector_id" not in saved
    finally:
        store.close()
    resumed = MeteringStore(path)
    try:
        state = resumed.load()
        assert state is not None
        assert state.schema_version == 2
        assert state.active_batch.batch_id == "a"
        assert state.pending_batches[0].batch_id == "pending"
        assert state.pending_batches[0].entries[0].total_tokens == 23
        assert marker.read_text() == "usage-state-v2"
        assert resumed.load() == state
        assert set(json.loads(path.read_text())) == {
            "schema_version",
            "active_batch",
            "pending_batches",
        }
    finally:
        resumed.close()


@pytest.mark.parametrize(
    "version,marker_value",
    [(1, "b" * 32), (1, "usage-state-v2"), (2, "bad marker"), (3, "a" * 32)],
)
def test_legacy_mismatch_and_unsupported_state_do_not_modify_file(tmp_path, version, marker_value):
    path = tmp_path / "usage.json"
    data = checkpoint().model_dump(mode="json")
    data["schema_version"] = version
    if version == 1:
        data["collector_id"] = "a" * 32
    path.write_text(json.dumps(data))
    marker = path.with_suffix(".json.initialized")
    marker.write_text(marker_value)
    before = path.read_bytes()
    store = MeteringStore(path)
    try:
        with pytest.raises(ValueError):
            store.load()
        assert path.read_bytes() == before
        assert marker.read_text() == marker_value
    finally:
        store.close()
