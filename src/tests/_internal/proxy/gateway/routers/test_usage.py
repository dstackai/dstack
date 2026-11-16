import httpx
import pytest

from dstack._internal.proxy.gateway.app import make_app
from dstack._internal.proxy.gateway.repo.repo import GatewayProxyRepo
from dstack._internal.proxy.gateway.services.metering_store import MeteringStore
from dstack._internal.proxy.lib.services.usage import VLLM_PROFILE
from tests._internal.proxy.gateway.services.test_metering import FakeClock, record


@pytest.mark.asyncio
async def test_fetch_and_ack_preserve_active_and_reject_active_ids(tmp_path):
    clock = FakeClock()
    store = MeteringStore(tmp_path / "usage.json")
    app = make_app(repo=GatewayProxyRepo(), metering_store=store, clock=clock)
    collector = app.state.proxy_dependency_injector.get_usage_observer()
    collector.profiles = {"s": VLLM_PROFILE}
    await collector.start()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://control"
    ) as client:
        await record(collector)
        clock.advance()
        await collector.rotate_if_due()
        response = await client.get("/api/usage/batches?limit=1")
        assert response.status_code == 200
        a = response.json()["batches"][0]
        assert (await client.get("/api/usage/batches")).json()["batches"] == [a]
        await record(collector)
        saved = store.load()
        assert saved is not None
        bad = await client.post(
            "/api/usage/batches/ack",
            json={"batch_ids": [a["batch_id"], saved.active_batch.batch_id]},
        )
        assert bad.status_code == 400
        assert (await client.get("/api/usage/batches")).json()["batches"] == [a]
        assert (
            await client.post("/api/usage/batches/ack", json={"batch_ids": [a["batch_id"]]})
        ).status_code == 200
        clock.advance()
        await collector.rotate_if_due()
        b = (await client.get("/api/usage/batches")).json()["batches"][0]
        await client.post("/api/usage/batches/ack", json={"batch_ids": [a["batch_id"]]})
        assert (await client.get("/api/usage/batches")).json()["batches"] == [b]
        assert b["entries"][0]["total_tokens"] == 23
        assert (await client.get("/api/usage/batches?limit=0")).status_code == 422
        assert (
            await client.post("/api/usage/batches/ack", json={"batch_ids": []})
        ).status_code == 422
    await collector.close()
