import httpx
import pytest

from dstack._internal.proxy.gateway.app import make_app
from dstack._internal.proxy.gateway.models import GlobalProxyConfig
from dstack._internal.proxy.gateway.repo.repo import GatewayProxyRepo
from dstack._internal.proxy.lib.testing.common import make_project, make_service


def make_client(repo: GatewayProxyRepo) -> httpx.AsyncClient:
    app = make_app(repo)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test/")


@pytest.mark.asyncio
class TestGetStateSummary:
    async def test_empty(self):
        async with make_client(GatewayProxyRepo()) as client:
            resp = await client.get("/api/state/get_summary")

        assert resp.status_code == 200
        assert resp.json() == {"services": [], "config_hash": None}

    async def test_returns_services_and_config_hash(self):
        repo = GatewayProxyRepo()
        await repo.set_project(make_project("test-proj"))
        await repo.set_service(make_service("test-proj", "srv-1", run_id="srv-1-id"))
        await repo.set_config(GlobalProxyConfig(config_hash="hash"))

        async with make_client(repo) as client:
            resp = await client.get("/api/state/get_summary")

        assert resp.status_code == 200
        assert [s["run_name"] for s in resp.json()["services"]] == ["srv-1"]
        assert resp.json()["config_hash"] == "hash"
