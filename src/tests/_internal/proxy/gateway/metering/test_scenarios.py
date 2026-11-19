"""DS-002 acceptance: real local HTTP/processes, deterministic inference and isolated state."""

import asyncio
import json
import time
from datetime import datetime, timezone

import httpx
import pytest

from dstack._internal.proxy.lib.schemas.usage import UsageBatchPage
from tests._internal.proxy.gateway.metering.harness import Harness
from tests._internal.proxy.gateway.metering.receiver import COUNTERS, MockReceiver
from tests._internal.proxy.gateway.metering.traffic import FIXTURES, TrafficDriver

PAIR = ("1" * 32, "a" * 32)


def totals(batch):
    return {name: sum(e[name] for e in batch["entries"]) for name in COUNTERS}


def expected(case, count=1):
    return {k: v * count for k, v in FIXTURES[case].items()}


async def send(h, driver, request_id, **kwargs):
    result = await driver.send(request_id, **kwargs)
    await h.wait_finalized(request_id)
    return result


async def close_minute(h):
    if not h.realtime:
        await h.advance_clock()
        return
    start = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    deadline = time.monotonic() + 70
    while time.monotonic() < deadline:
        page = await h.batches()
        if any(datetime.fromisoformat(b["interval_start"]) >= start for b in page["batches"]):
            return
        await asyncio.sleep(0.2)
    raise TimeoutError("Minute did not durably close")


async def two_intervals(h):
    driver = TrafficDriver(h.gateway_url, artifact_dir=h.state)
    receiver = MockReceiver(
        h.gateway_url,
        h.state / "receiver.sqlite",
        gateway_replica_id="replica-a",
        gateway_id="gateway-a",
    )
    evidence: dict = {"started_at": datetime.now(timezone.utc).isoformat()}
    try:
        for i in range(10):
            await send(h, driver, f"A-{i}", stream=i % 2 == 0)
        await close_minute(h)
        page = await h.batches()
        a = page["batches"][-1]
        evidence["A"] = a
        assert totals(a) == expected("A", 10)
        assert a in (await h.batches())["batches"]
        receiver.commit_page(UsageBatchPage.model_validate({**page, "batches": [a]}))
        await send(h, driver, "B-0", case="B")
        await h.backend_control(hold=["B-1"])
        inflight = asyncio.create_task(send(h, driver, "B-1", case="B", stream=True))
        await h.wait_backend_started("B-1")
        evidence["ack_A"] = (await receiver.acknowledge_committed([a["batch_id"]])).model_dump()
        assert a["batch_id"] not in [b["batch_id"] for b in (await h.batches())["batches"]]
        await h.backend_control(release=["B-1"])
        await inflight
        for i in range(2, 7):
            await send(h, driver, f"B-{i}", case="B", stream=i % 2 == 0)
        await close_minute(h)
        b = (await h.batches())["batches"][-1]
        evidence["B"] = b
        assert totals(b) == expected("B", 7)
        await receiver.acknowledge_committed([a["batch_id"]])
        assert b in (await h.batches())["batches"]
        await receiver.collect_once()
        assert receiver.totals()[PAIR] == dict(zip(COUNTERS, [340, 50, 58, 398, 0]))
        assert not (await h.batches())["batches"]
        evidence["ledger_totals"] = [
            {"subject": k[0], "service": k[1], **v} for k, v in receiver.totals().items()
        ]
    finally:
        evidence["traffic"] = driver.report.attempts
        evidence["finished_at"] = datetime.now(timezone.utc).isoformat()
        (h.state / "evidence.json").write_text(json.dumps(evidence, indent=2))
        await driver.close()
        await receiver.close()


@pytest.mark.asyncio
async def test_two_intervals_and_ack(harness):
    await two_intervals(harness)


@pytest.mark.asyncio
async def test_drain_allows_open_stream_to_deliver_its_final_usage(harness):
    h = harness
    driver = TrafficDriver(h.gateway_url, artifact_dir=h.state)
    try:
        await h.backend_control(hold=["draining-stream"])
        stream = asyncio.create_task(send(h, driver, "draining-stream", stream=True))
        try:
            await h.wait_backend_started("draining-stream")
            async with httpx.AsyncClient(base_url=h.gateway_url, timeout=10) as control:
                response = await control.post("/api/usage/drain")
                assert response.json() == {"sealed": False, "empty": False}
                with pytest.raises(httpx.HTTPStatusError) as exc:
                    await driver.send("after-fence")
                assert exc.value.response.status_code == 503
        finally:
            await h.backend_control(release=["draining-stream"])
            await stream
        # No clock advance: the final usage-only SSE event must be present immediately.
        async with httpx.AsyncClient(base_url=h.gateway_url, timeout=10) as control:
            response = await control.post("/api/usage/drain")
            assert response.json() == {"sealed": True, "empty": False}
            (batch,) = (await h.batches())["batches"]
            assert totals(batch) == expected("A")
            ack = await control.post(
                "/api/usage/batches/ack", json={"batch_ids": [batch["batch_id"]]}
            )
            ack.raise_for_status()
            assert (await control.post("/api/usage/drain")).json() == {
                "sealed": True,
                "empty": True,
            }
    finally:
        await driver.close()


@pytest.mark.asyncio
async def test_selective_ack_during_traffic(harness):
    h = harness
    d = TrafficDriver(h.gateway_url, artifact_dir=h.state)
    r = MockReceiver(
        h.gateway_url,
        h.state / "receiver.sqlite",
        gateway_replica_id="replica-a",
        gateway_id="gateway-a",
    )
    try:
        await send(h, d, "P")
        await close_minute(h)
        p = (await h.batches())["batches"][0]
        await send(h, d, "Q", case="C")
        await close_minute(h)
        page = await h.batches()
        q = page["batches"][1]
        r.commit_page(UsageBatchPage.model_validate({**page, "batches": [p]}))
        await send(h, d, "R0", case="D")
        await h.backend_control(hold=["R1"])
        task = asyncio.create_task(send(h, d, "R1", case="D"))
        await h.wait_backend_started("R1")
        await r.acknowledge_committed([p["batch_id"]])
        assert (await h.batches())["batches"] == [q]
        await h.backend_control(release=["R1"])
        await task
        await close_minute(h)
        batches = (await h.batches())["batches"]
        assert batches[0] == q and totals(batches[1]) == expected("D", 2)
    finally:
        await d.close()
        await r.close()


@pytest.mark.asyncio
async def test_subject_service_isolation(harness):
    h = harness
    d = TrafficDriver(h.gateway_url, artifact_dir=h.state)
    try:
        cases = [
            ("token-a", "model-a", "A"),
            ("token-a", "model-b", "B"),
            ("token-b", "model-a", "C"),
            ("token-b", "model-b", "D"),
        ]
        await asyncio.gather(
            *(
                send(h, d, f"spoofed-user-{i}", case=c, token=t, model=m, stream=True)
                for i, (t, m, c) in enumerate(cases)
            )
        )
        await close_minute(h)
        entries = (await h.batches())["batches"][0]["entries"]
        actual = {
            (e["consumer_subject_id"], e["service_id"]): {k: e[k] for k in COUNTERS}
            for e in entries
        }
        assert actual == {
            (str(1 + i // 2) * 32, ("a" if i % 2 == 0 else "b") * 32): expected(c)
            for i, (_, _, c) in enumerate(cases)
        }
    finally:
        await d.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("case", ["A", "B"])
async def test_json_and_streaming_usage(harness, stream, case):
    h = harness
    d = TrafficDriver(h.gateway_url, artifact_dir=h.state)
    try:
        await send(h, d, "request", case=case, stream=stream)
        await close_minute(h)
        assert totals((await h.batches())["batches"][0]) == expected(case)
    finally:
        await d.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("after_usage", [False, True])
async def test_stream_disconnect(harness, after_usage):
    h = harness
    await h.backend_control(hold=["disconnect"], after_usage=after_usage)
    body = {
        "model": "model-a",
        "user": "disconnect",
        "messages": [{"role": "user", "content": "A"}],
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    async with httpx.AsyncClient(base_url=h.gateway_url, timeout=10) as client:
        async with client.stream(
            "POST",
            "/api/models/p/chat/completions",
            json=body,
            headers={"Authorization": "Bearer token-a", "X-Test-Request-ID": "disconnect"},
        ) as response:
            response.raise_for_status()
            saw_content = False
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                event = json.loads(line[5:])
                saw_content |= bool(event.get("choices"))
                if (not after_usage and saw_content) or (after_usage and event.get("usage")):
                    break
            assert saw_content  # Content arrives while final usage / DONE is still held.
    await h.wait_finalized("disconnect")
    await close_minute(h)
    assert totals((await h.batches())["batches"][0]) == expected("A" if after_usage else "cut")
    await h.backend_control(release=["disconnect"])


@pytest.mark.asyncio
async def test_truncated_stream_unknown(harness):
    h = harness
    d = TrafficDriver(h.gateway_url, artifact_dir=h.state)
    try:
        await send(h, d, "cut", case="cut", stream=True)
        await close_minute(h)
        assert totals((await h.batches())["batches"][0]) == expected("cut")
    finally:
        await d.close()


class LostReply(httpx.AsyncBaseTransport):
    def __init__(self, method):
        self.inner = httpx.AsyncHTTPTransport()
        self.method = method
        self.lost = False

    async def handle_async_request(self, request):
        response = await self.inner.handle_async_request(request)
        if request.method == self.method and not self.lost:
            self.lost = True
            await response.aread()
            await response.aclose()
            raise httpx.ReadError("Injected lost response", request=request)
        return response

    async def aclose(self):
        await self.inner.aclose()


@pytest.mark.asyncio
async def test_receiver_outage_and_retry(harness):
    h = harness
    d = TrafficDriver(h.gateway_url, artifact_dir=h.state)
    ledger = h.state / "receiver.sqlite"
    try:
        for i in range(2):
            await send(h, d, f"offline-{i}")
            await close_minute(h)
        pending = (await h.batches())["batches"]
        assert len(pending) == 2
        async with httpx.AsyncClient(base_url=h.gateway_url, transport=LostReply("GET")) as client:
            r = MockReceiver(
                h.gateway_url,
                ledger,
                client,
                gateway_replica_id="replica-a",
                gateway_id="gateway-a",
            )
            with pytest.raises(httpx.ReadError):
                await r.collect_once(1)
            assert r.receipt_ids() == [] and (await h.batches())["batches"] == pending
            first = await r.collect_once(1, acknowledge=False)
            await r.close()
        r = MockReceiver(
            h.gateway_url, ledger, gateway_replica_id="replica-a", gateway_id="gateway-a"
        )
        replay = await r.collect_once(1, acknowledge=False)
        assert replay.replayed_ids == first.committed_ids
        await r.close()
        async with httpx.AsyncClient(
            base_url=h.gateway_url, transport=LostReply("POST")
        ) as client:
            r = MockReceiver(
                h.gateway_url,
                ledger,
                client,
                gateway_replica_id="replica-a",
                gateway_id="gateway-a",
            )
            with pytest.raises(httpx.ReadError):
                await r.acknowledge_committed(first.committed_ids)
            assert len((await h.batches())["batches"]) == 1
            await r.acknowledge_committed(first.committed_ids)
            await r.collect_once(1)
            assert len(r.receipt_ids()) == 2 and r.totals()[PAIR] == expected("A", 2)
            assert (await h.batches())["batches"] == []
            await r.close()
    finally:
        await d.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("kill", [False, True])
async def test_gateway_restart_persistence(harness, kill):
    h = harness
    d = TrafficDriver(h.gateway_url, artifact_dir=h.state)
    r = MockReceiver(
        h.gateway_url,
        h.state / "receiver.sqlite",
        gateway_replica_id="replica-a",
        gateway_id="gateway-a",
    )
    try:
        await send(h, d, "P")
        await close_minute(h)
        await r.collect_once()
        await send(h, d, "Q", case="B")
        await close_minute(h)
        page = await h.batches()
        q = page["batches"][0]
        await d.close()
        await r.close()
        await h.restart(kill)
        assert (await h.batches()) == page
        d = TrafficDriver(h.gateway_url, artifact_dir=h.state)
        r = MockReceiver(
            h.gateway_url,
            h.state / "receiver.sqlite",
            gateway_replica_id="replica-a",
            gateway_id="gateway-a",
        )
        await r.collect_once()
        await send(h, d, "R", case="C")
        await close_minute(h)
        new = (await h.batches())["batches"][0]
        assert new["batch_id"] != q["batch_id"] and totals(new) == expected("C")
        await r.collect_once()
        assert len(r.receipt_ids()) == 3
    finally:
        await d.close()
        await r.close()


@pytest.mark.asyncio
async def test_unsaved_active_loss_is_bounded(harness):
    h = harness
    d = TrafficDriver(h.gateway_url, artifact_dir=h.state)
    try:
        await send(h, d, "durable")
        await h.ipc_command("checkpoint")
        await send(h, d, "unsaved", case="B")
        await d.close()
        await h.restart(kill=True)
        await close_minute(h)
        assert totals((await h.batches())["batches"][0]) == expected("A")
    finally:
        await d.close()


@pytest.mark.metering_realtime
@pytest.mark.asyncio
async def test_two_intervals_real_minutes(tmp_path):
    h = Harness(tmp_path, realtime=True)
    await h.start()
    try:
        # Align without wall-clock sleeps in the default suite; this explicit opt-in is acceptance evidence.
        deadline = time.monotonic() + 65
        while datetime.now(timezone.utc).second > 2:
            if time.monotonic() > deadline:
                raise TimeoutError("Could not align minute")
            await asyncio.sleep(0.2)
        await two_intervals(h)
    finally:
        await h.stop()


@pytest.mark.asyncio
async def test_subject_service_totals_across_two_gateway_replicas(tmp_path):
    # Separate processes exercise source attribution through actual HTTP endpoints,
    # not just synthetic pages passed straight into the receiver.
    gateways = [Harness(tmp_path / f"gateway-{i}") for i in range(2)]
    drivers, receivers = [], []
    try:
        for i, h in enumerate(gateways):
            await h.start()
            driver = TrafficDriver(h.gateway_url)
            drivers.append(driver)
            receivers.append(
                MockReceiver(
                    h.gateway_url,
                    tmp_path / "shared.sqlite",
                    gateway_replica_id=f"replica-{i}",
                    gateway_id="logical-gateway",
                )
            )
            await send(h, driver, f"request-{i}", case="A")
            await h.advance_clock()
            page = await h.batches()
            assert page["schema_version"] == 2 and "collector_id" not in page
            await receivers[-1].collect_once()
            assert not (await h.batches())["batches"]
        assert receivers[0].totals()[PAIR] == dict(
            prompt_tokens=40,
            cached_prompt_tokens=10,
            completion_tokens=6,
            total_tokens=46,
            unknown_usage_attempts=0,
        )
        rows = (
            receivers[0]
            .db.execute(
                "SELECT gateway_id,COUNT(DISTINCT gateway_replica_id),COUNT(*) "
                "FROM receipts GROUP BY gateway_id"
            )
            .fetchall()
        )
        assert rows == [("logical-gateway", 2, 2)]
    finally:
        for driver in drivers:
            await driver.close()
        for receiver in receivers:
            await receiver.close()
        for h in gateways:
            await h.stop()
