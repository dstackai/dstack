import uuid

import httpx
import pytest

from dstack._internal.proxy.gateway.app import make_app
from dstack._internal.proxy.gateway.repo.repo import GatewayProxyRepo
from dstack._internal.proxy.lib.models import Replica
from dstack._internal.proxy.lib.testing.common import make_project, make_service


def make_client(repo: GatewayProxyRepo) -> httpx.AsyncClient:
    app = make_app(repo)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test/")


@pytest.mark.asyncio
class TestListServices:
    async def test_empty(self):
        repo = GatewayProxyRepo()
        client = make_client(repo)
        resp = await client.get("/api/services/list")
        assert resp.status_code == 200
        assert resp.json() == {"services": []}

    async def test_list(self):
        repo = GatewayProxyRepo()
        service_id = uuid.uuid4().hex
        replica_id = uuid.uuid4().hex
        service = make_service(
            "test-proj", "srv-1", domain="srv-1.gtw.test", run_id=service_id
        ).with_replicas(
            [
                Replica(
                    id=replica_id,
                    app_port=80,
                    ssh_destination="ubuntu@server",
                    ssh_port=22,
                    ssh_proxy=None,
                )
            ]
        )
        await repo.set_project(make_project("test-proj"))
        await repo.set_service(service)
        client = make_client(repo)
        resp = await client.get("/api/services/list")
        assert resp.status_code == 200
        assert resp.json() == {
            "services": [
                {
                    "id": service_id,
                    "project_name": "test-proj",
                    "run_name": "srv-1",
                    "replicas": [{"id": replica_id}],
                }
            ]
        }
