import sqlite3

import httpx
import pytest

from dstack._internal.proxy.lib.schemas.usage import UsageBatchPage
from tests._internal.proxy.gateway.metering.harness import Harness
from tests._internal.proxy.gateway.metering.receiver import MockReceiver
from tests._internal.proxy.gateway.metering.traffic import TrafficDriver


def page(batch_id="a", completion=3):
    return UsageBatchPage.model_validate(
        {
            "batches": [
                {
                    "batch_id": batch_id,
                    "interval_start": "2026-11-16T10:00:00Z",
                    "interval_end": "2026-11-16T10:01:00Z",
                    "entries": [
                        {
                            "consumer_subject_id": "u",
                            "service_id": "s",
                            "prompt_tokens": 20,
                            "cached_prompt_tokens": 5,
                            "completion_tokens": completion,
                            "total_tokens": 20 + completion,
                            "unknown_usage_attempts": 0,
                        }
                    ],
                }
            ],
        }
    )


@pytest.mark.asyncio
async def test_receiver_commits_once_reopens_and_rejects_conflicting_content(tmp_path):
    ledger = tmp_path / "receiver.sqlite"
    receiver = MockReceiver(
        "http://unused", ledger, gateway_replica_id="replica-a", gateway_id="gateway"
    )
    assert receiver.commit_page(page()) == (["a"], [])
    assert receiver.commit_page(page()) == ([], ["a"])
    with pytest.raises(ValueError, match="content"):
        receiver.commit_page(page(completion=4))
    assert receiver.totals()[("u", "s")] == dict(
        prompt_tokens=20,
        cached_prompt_tokens=5,
        completion_tokens=3,
        total_tokens=23,
        unknown_usage_attempts=0,
    )
    await receiver.close()
    receiver = MockReceiver(
        "http://unused", ledger, gateway_replica_id="replica-a", gateway_id="gateway"
    )
    assert receiver.commit_page(page()) == ([], ["a"])
    assert receiver.totals()[("u", "s")]["total_tokens"] == 23
    with pytest.raises(ValueError, match="committed"):
        await receiver.acknowledge_committed(["unseen"])
    await receiver.close()


@pytest.mark.asyncio
async def test_receiver_page_conflict_rolls_back_other_new_batches(tmp_path):
    receiver = MockReceiver(
        "http://unused",
        tmp_path / "receiver.sqlite",
        gateway_replica_id="replica-a",
        gateway_id="gateway",
    )
    receiver.commit_page(page())
    mixed = UsageBatchPage(batches=[page("new").batches[0], page(completion=4).batches[0]])
    with pytest.raises(ValueError):
        receiver.commit_page(mixed)
    assert receiver.receipt_ids() == ["a"]
    await receiver.close()


@pytest.mark.asyncio
async def test_traffic_checks_independent_expected_usage():
    wrong = {
        "id": "answer",
        "model": "model-a",
        "choices": [],
        "created": 1,
        "usage": {
            "prompt_tokens": 20,
            "completion_tokens": 3,
            "total_tokens": 23,
            "prompt_tokens_details": {"cached_tokens": 0},
        },
    }
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=wrong)),
        base_url="http://gateway",
    ) as client:
        driver = TrafficDriver("http://gateway", client=client)
        with pytest.raises(AssertionError, match="usage"):
            await driver.send("request-1", case="A")


@pytest.mark.asyncio
async def test_separate_gateway_uses_real_model_and_management_routes(tmp_path):
    harness = Harness(tmp_path)
    await harness.start()
    driver = TrafficDriver(harness.gateway_url)
    try:
        await driver.send("first", case="A", stream=True)
        await harness.wait_finalized("first")
        assert not (await harness.batches())["batches"]
        await harness.advance_clock()
        batch = (await harness.batches())["batches"][0]
        assert batch["entries"][0]["cached_prompt_tokens"] == 5
        assert batch["entries"][0]["consumer_subject_id"] == "1" * 32
    finally:
        await driver.close()
        await harness.stop()


@pytest.mark.asyncio
async def test_receiver_shared_ledger_scopes_replay_and_ack_to_replica(tmp_path):
    ledger = tmp_path / "receiver.sqlite"
    first = MockReceiver("http://one", ledger, gateway_replica_id="r1", gateway_id="g")
    second = MockReceiver("http://two", ledger, gateway_replica_id="r2", gateway_id="g")
    try:
        first.commit_page(page("only-first"))
        with pytest.raises(ValueError, match="committed"):
            await second.acknowledge_committed(["only-first"])
        first.commit_page(page("shared"))
        second.commit_page(page("shared", completion=4))
        assert second.commit_page(page("shared", completion=4)) == ([], ["shared"])
        assert first.receipt_ids() == ["only-first", "shared"]
        assert second.receipt_ids() == ["shared"]
        assert first.totals()[("u", "s")]["completion_tokens"] == 10
        assert first.db.execute(
            "SELECT gateway_id, COUNT(*) FROM receipts GROUP BY gateway_id"
        ).fetchall() == [("g", 3)]
    finally:
        await first.close()
        await second.close()


def test_receiver_refuses_legacy_ledger_without_modifying_it(tmp_path):
    ledger = tmp_path / "old.sqlite"
    with sqlite3.connect(ledger) as db:
        db.execute("CREATE TABLE metadata (collector_id TEXT PRIMARY KEY)")
        db.execute("INSERT INTO metadata VALUES ('old')")
    before = ledger.read_bytes()
    with pytest.raises(ValueError, match="legacy"):
        MockReceiver("http://unused", ledger, gateway_replica_id="r", gateway_id="g")
    assert ledger.read_bytes() == before
