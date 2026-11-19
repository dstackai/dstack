import httpx
import pytest

from dstack._internal.proxy.gateway.app import make_app
from dstack._internal.proxy.gateway.repo.repo import GatewayProxyRepo
from dstack._internal.proxy.gateway.services.metering_store import MeteringStore
from dstack._internal.proxy.gateway.services.nginx import Nginx
from dstack._internal.proxy.lib.errors import ProxyError
from dstack._internal.proxy.lib.schemas.usage import UsageKey
from dstack._internal.proxy.lib.services.usage import VLLM_PROFILE
from tests._internal.proxy.gateway.services.test_metering import FakeClock, record


class DrainingNginx(Nginx):
    idle = True

    async def drain(self) -> bool:
        return self.idle


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


@pytest.mark.asyncio
async def test_drain_of_unused_replica_is_durable_before_profiles_are_configured(tmp_path):
    path = tmp_path / "usage.json"
    for restart in [False, True]:
        app = make_app(
            repo=GatewayProxyRepo(), metering_store=MeteringStore(path), nginx=DrainingNginx()
        )
        collector = app.state.proxy_dependency_injector.get_metering()
        await collector.start()
        try:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://control"
            ) as client:
                if restart:
                    await collector.configure_profiles({"s": VLLM_PROFILE})
                    with pytest.raises(ProxyError) as exc:
                        collector.start_attempt(
                            UsageKey(consumer_subject_id="u", service_id="s"), VLLM_PROFILE
                        )
                    assert exc.value.status_code == 503
                response = await client.post("/api/usage/drain")
                assert response.status_code == 200
                assert response.json() == {"sealed": True, "empty": True}
                assert (await client.get("/api/usage/batches")).json()["batches"] == []
        finally:
            await collector.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("kill", [True, False])
async def test_traffic_accepted_by_old_nginx_worker_with_gateway_restart(tmp_path, kill):
    store = MeteringStore(tmp_path / "usage.json")
    nginx = DrainingNginx()
    nginx.idle = False
    clock = FakeClock()
    app = make_app(repo=GatewayProxyRepo(), nginx=nginx, metering_store=store, clock=clock)
    collector = app.state.proxy_dependency_injector.get_metering()
    await collector.configure_profiles({"s": VLLM_PROFILE})
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://control"
    ) as client:
        assert (await client.post("/api/usage/drain")).json() == {"sealed": False, "empty": False}
        # A request already accepted by the retiring worker can still reach Python.
        await record(collector)
        if kill:
            store.close()
        else:
            await collector.close()

    app = make_app(
        repo=GatewayProxyRepo(), nginx=nginx, metering_store=MeteringStore(store.path), clock=clock
    )
    collector = app.state.proxy_dependency_injector.get_metering()
    await collector.configure_profiles({"s": VLLM_PROFILE})
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://control"
        ) as client:
            if not kill:
                # A request buffered in an old Nginx worker enters Python after restart.
                await record(collector)
            nginx.idle = True
            result = await client.post("/api/usage/drain")
            if kill:
                assert result.status_code == 503
            else:
                assert result.json() == {"sealed": True, "empty": False}
                (batch,) = (await client.get("/api/usage/batches")).json()["batches"]
                assert batch["entries"][0]["total_tokens"] == 46
            with pytest.raises(ProxyError):
                await record(collector)
    finally:
        await collector.close()


@pytest.mark.asyncio
async def test_final_ack_still_requires_current_ingress_proof(tmp_path):
    nginx = DrainingNginx()
    app = make_app(
        repo=GatewayProxyRepo(), nginx=nginx, metering_store=MeteringStore(tmp_path / "usage.json")
    )
    collector = app.state.proxy_dependency_injector.get_metering()
    await collector.configure_profiles({"s": VLLM_PROFILE})
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://control"
        ) as client:
            await record(collector)
            assert (await client.post("/api/usage/drain")).json() == {
                "sealed": True,
                "empty": False,
            }
            (batch,) = (await client.get("/api/usage/batches")).json()["batches"]
            ack = await client.post(
                "/api/usage/batches/ack", json={"batch_ids": [batch["batch_id"]]}
            )
            ack.raise_for_status()
            nginx.idle = False
            assert (await client.post("/api/usage/drain")).json() == {
                "sealed": False,
                "empty": False,
            }
            nginx.idle = True
            assert (await client.post("/api/usage/drain")).json() == {
                "sealed": True,
                "empty": True,
            }
    finally:
        await collector.close()
