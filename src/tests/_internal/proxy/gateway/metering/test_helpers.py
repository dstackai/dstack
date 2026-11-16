import httpx
import pytest

from dstack._internal.proxy.lib.schemas.usage import UsageBatchPage
from tests._internal.proxy.gateway.metering.harness import Harness
from tests._internal.proxy.gateway.metering.receiver import MockReceiver
from tests._internal.proxy.gateway.metering.traffic import TrafficDriver


def page(batch_id="a", completion=3):
    return UsageBatchPage.model_validate(
        {
            "collector_id": "collector",
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
    receiver = MockReceiver("http://unused", ledger)
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
    receiver = MockReceiver("http://unused", ledger)
    assert receiver.commit_page(page()) == ([], ["a"])
    assert receiver.totals()[("u", "s")]["total_tokens"] == 23
    with pytest.raises(ValueError, match="committed"):
        await receiver.acknowledge_committed(["unseen"])
    await receiver.close()


@pytest.mark.asyncio
async def test_receiver_page_conflict_rolls_back_other_new_batches(tmp_path):
    receiver = MockReceiver("http://unused", tmp_path / "receiver.sqlite")
    receiver.commit_page(page())
    mixed = UsageBatchPage(
        collector_id="collector", batches=[page("new").batches[0], page(completion=4).batches[0]]
    )
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
