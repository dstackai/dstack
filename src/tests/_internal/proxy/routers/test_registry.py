import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Generator, Optional, Union
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from freezegun import freeze_time

from dstack._internal.proxy.app import make_app
from dstack._internal.proxy.repos.gateway import GatewayProxyRepo
from dstack._internal.proxy.repos.models import ChatModel, OpenAIChatModelFormat
from dstack._internal.proxy.services.nginx import Nginx

AnyMock = Union[MagicMock, AsyncMock]


@dataclass
class Mocks:
    reload_nginx: AnyMock
    run_certbot: AnyMock
    open_conn: AnyMock
    close_conn: AnyMock


@pytest.fixture
def system_mocks() -> Generator[Mocks, None, None]:
    nginx = "dstack._internal.proxy.services.nginx"
    connection = "dstack._internal.proxy.services.service_connection"
    with (
        patch(f"{nginx}.sudo") as sudo,
        patch(f"{nginx}.Nginx.reload") as reload_nginx,
        patch(f"{nginx}.Nginx.run_certbot") as run_certbot,
        patch(f"{connection}.ServiceReplicaConnection.open") as open_conn,
        patch(f"{connection}.ServiceReplicaConnection.close") as close_conn,
    ):
        sudo.return_value = []
        yield Mocks(
            reload_nginx=reload_nginx,
            run_certbot=run_certbot,
            open_conn=open_conn,
            close_conn=close_conn,
        )


def make_client(
    nginx_conf_dir: Path, repo: Optional[GatewayProxyRepo] = None
) -> httpx.AsyncClient:
    app = make_app(repo=repo or GatewayProxyRepo(), nginx=Nginx(conf_dir=nginx_conf_dir))
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test/")


def register_service_payload(
    run_name: str = "test-run",
    domain: str = "test-run.gtw.test",
    https: bool = False,
    auth: bool = False,
    client_max_body_size: int = 1024,
    options: Optional[dict] = None,
) -> dict:
    return {
        "run_name": run_name,
        "domain": domain,
        "https": https,
        "auth": auth,
        "client_max_body_size": client_max_body_size,
        "options": options or {},
        "ssh_private_key": "private-key",
    }


def register_replica_payload(job_id: str = "xxx-xxx") -> dict:
    return {
        "job_id": job_id,
        "app_port": 8888,
        "ssh_host": "host.test",
        "ssh_port": 22,
        "ssh_proxy": None,
    }


def sample_model_options(name: str = "test-model") -> dict:
    return {
        "openai": {
            "model": {
                "type": "chat",
                "name": name,
                "format": "openai",
                "prefix": "/v1",
            }
        }
    }


@pytest.mark.asyncio
class TestRegisterService:
    async def test_register(self, tmp_path: Path, system_mocks: Mocks) -> None:
        client = make_client(tmp_path)
        resp = await client.post(
            "/api/registry/test-proj/services/register",
            json=register_service_payload(
                run_name="test-run",
                domain="test-run.gtw.test",
                https=False,
                auth=False,
                client_max_body_size=1024,
            ),
        )
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}
        conf = (tmp_path / "443-test-run.gtw.test.conf").read_text()
        # general
        assert system_mocks.reload_nginx.call_count == 1
        assert "server_name test-run.gtw.test;" in conf
        assert "client_max_body_size 1024;" in conf
        assert "listen 80;" in conf
        # no https
        assert system_mocks.run_certbot.call_count == 0
        assert "listen 443" not in conf
        # no auth
        assert "auth_request /auth;" not in conf
        # no replicas
        assert "upstream test-run" not in conf
        assert "return 503;" in conf

    async def test_register_with_https(self, tmp_path: Path, system_mocks: Mocks) -> None:
        client = make_client(tmp_path)
        resp = await client.post(
            "/api/registry/test-proj/services/register",
            json=register_service_payload(domain="test-run.gtw.test", https=True),
        )
        assert resp.status_code == 200
        conf = (tmp_path / "443-test-run.gtw.test.conf").read_text()
        assert "listen 80;" in conf
        assert "listen 443 ssl;" in conf
        assert "ssl_certificate /etc/letsencrypt/live/test-run.gtw.test/fullchain.pem;" in conf
        assert "ssl_certificate_key /etc/letsencrypt/live/test-run.gtw.test/privkey.pem;" in conf
        assert system_mocks.run_certbot.call_count == 1

    async def test_register_with_auth(self, tmp_path: Path, system_mocks: Mocks) -> None:
        client = make_client(tmp_path)
        resp = await client.post(
            "/api/registry/test-proj/services/register",
            json=register_service_payload(domain="test-run.gtw.test", auth=True),
        )
        assert resp.status_code == 200
        conf = (tmp_path / "443-test-run.gtw.test.conf").read_text()
        assert "auth_request /auth;" in conf
        assert "proxy_pass http://localhost:8000/api/auth/test-proj;" in conf

    async def test_register_same_name_error(self, tmp_path: Path, system_mocks: Mocks) -> None:
        client = make_client(tmp_path)
        resp = await client.post(
            "/api/registry/test-proj/services/register",
            json=register_service_payload(run_name="test-run", domain="test-run-1.gtw.test"),
        )
        assert resp.status_code == 200
        resp = await client.post(
            "/api/registry/test-proj/services/register",
            json=register_service_payload(run_name="test-run", domain="test-run-2.gtw.test"),
        )
        assert resp.status_code == 400
        assert resp.json() == {"detail": "Service test-proj/test-run is already registered"}
        assert (tmp_path / "443-test-run-1.gtw.test.conf").exists()
        assert not (tmp_path / "443-test-run-2.gtw.test.conf").exists()
        assert system_mocks.reload_nginx.call_count == 1

    async def test_register_same_name_in_different_projects(
        self, tmp_path: Path, system_mocks
    ) -> None:
        client = make_client(tmp_path)
        resp = await client.post(
            "/api/registry/proj-1/services/register",
            json=register_service_payload(run_name="test-run", domain="test-run.proj-1.gtw.test"),
        )
        assert resp.status_code == 200
        resp = await client.post(
            "/api/registry/proj-2/services/register",
            json=register_service_payload(run_name="test-run", domain="test-run.proj-2.gtw.test"),
        )
        assert resp.status_code == 200
        assert (tmp_path / "443-test-run.proj-1.gtw.test.conf").exists()
        assert (tmp_path / "443-test-run.proj-2.gtw.test.conf").exists()

    @freeze_time(datetime(2024, 12, 12, 0, 30))
    async def test_register_with_model(self, tmp_path: Path, system_mocks: Mocks) -> None:
        repo = GatewayProxyRepo()
        client = make_client(tmp_path, repo=repo)
        resp = await client.post(
            "/api/registry/test-proj/services/register",
            json=register_service_payload(
                run_name="test-run",
                options=sample_model_options(name="test-model"),
            ),
        )
        assert resp.status_code == 200
        assert await repo.list_models("test-proj") == [
            ChatModel(
                project_name="test-proj",
                name="test-model",
                created_at=datetime(2024, 12, 12, 0, 30),
                run_name="test-run",
                format_spec=OpenAIChatModelFormat(prefix="/v1"),
            )
        ]


@pytest.mark.asyncio
class TestRegisterReplica:
    async def test_register(self, tmp_path: Path, system_mocks: Mocks) -> None:
        client = make_client(tmp_path)
        # register service
        resp = await client.post(
            "/api/registry/test-proj/services/register",
            json=register_service_payload(run_name="test-run", domain="test-run.gtw.test"),
        )
        assert resp.status_code == 200
        conf = (tmp_path / "443-test-run.gtw.test.conf").read_text()
        assert "upstream test-run" not in conf
        # register 2 replicas
        for job_id in ("xxx-xxx", "yyy-yyy"):
            resp = await client.post(
                "/api/registry/test-proj/services/test-run/replicas/register",
                json=register_replica_payload(job_id=job_id),
            )
            assert resp.status_code == 200
            assert resp.json() == {"status": "ok"}
        conf = (tmp_path / "443-test-run.gtw.test.conf").read_text()
        assert "upstream test-run" in conf
        assert (m1 := re.search(r"server unix:/(.+)/replica.sock;  # replica xxx-xxx", conf))
        assert (m2 := re.search(r"server unix:/(.+)/replica.sock;  # replica yyy-yyy", conf))
        assert m1.group(1) != m2.group(1)
        assert system_mocks.reload_nginx.call_count == 3
        assert system_mocks.open_conn.call_count == 2

    async def test_register_no_service_error(self, tmp_path: Path, system_mocks: Mocks) -> None:
        client = make_client(tmp_path)
        resp = await client.post(
            "/api/registry/test-proj/services/test-run/replicas/register",
            json=register_replica_payload(),
        )
        assert resp.status_code == 400
        assert resp.json() == {
            "detail": "Service test-proj/test-run does not exist, cannot register replica"
        }
        assert system_mocks.reload_nginx.call_count == 0
        assert system_mocks.open_conn.call_count == 0


@pytest.mark.asyncio
class TestUnregisterService:
    async def test_unregister(self, tmp_path: Path, system_mocks: Mocks) -> None:
        client = make_client(tmp_path)
        # register service
        resp = await client.post(
            "/api/registry/test-proj/services/register",
            json=register_service_payload(run_name="test-run", domain="test-run.gtw.test"),
        )
        assert resp.status_code == 200
        assert (tmp_path / "443-test-run.gtw.test.conf").exists()
        # unregister service
        resp = await client.post("/api/registry/test-proj/services/test-run/unregister")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}
        assert not (tmp_path / "443-test-run.gtw.test.conf").exists()
        assert system_mocks.reload_nginx.call_count == 2

    async def test_unregister_not_registered_error(
        self, tmp_path: Path, system_mocks: Mocks
    ) -> None:
        client = make_client(tmp_path)
        resp = await client.post("/api/registry/test-proj/services/test-run/unregister")
        assert resp.status_code == 400
        assert resp.json() == {
            "detail": "Service test-proj/test-run is not registered, cannot unregister"
        }
        assert system_mocks.reload_nginx.call_count == 0

    async def test_unregister_with_replicas(self, tmp_path: Path, system_mocks: Mocks) -> None:
        client = make_client(tmp_path)
        # register service
        resp = await client.post(
            "/api/registry/test-proj/services/register",
            json=register_service_payload(run_name="test-run", domain="test-run.gtw.test"),
        )
        assert resp.status_code == 200
        # register 2 replicas
        for job_id in ("xxx-xxx", "yyy-yyy"):
            resp = await client.post(
                "/api/registry/test-proj/services/test-run/replicas/register",
                json=register_replica_payload(job_id=job_id),
            )
            assert resp.status_code == 200
        assert (tmp_path / "443-test-run.gtw.test.conf").exists()
        # unregister service
        resp = await client.post("/api/registry/test-proj/services/test-run/unregister")
        assert resp.status_code == 200
        assert not (tmp_path / "443-test-run.gtw.test.conf").exists()
        assert system_mocks.reload_nginx.call_count == 4
        assert system_mocks.close_conn.call_count == 2

    async def test_unregister_with_model(self, tmp_path: Path, system_mocks: Mocks) -> None:
        repo = GatewayProxyRepo()
        client = make_client(tmp_path, repo=repo)
        # register service
        resp = await client.post(
            "/api/registry/test-proj/services/register",
            json=register_service_payload(run_name="test-run", options=sample_model_options()),
        )
        assert resp.status_code == 200
        assert len(await repo.list_models("test-proj")) == 1
        # unregister service
        resp = await client.post("/api/registry/test-proj/services/test-run/unregister")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}
        assert len(await repo.list_models("test-proj")) == 0


@pytest.mark.asyncio
class TestUnregisterReplica:
    async def test_unregister(self, tmp_path: Path, system_mocks: Mocks) -> None:
        client = make_client(tmp_path)
        # register service
        resp = await client.post(
            "/api/registry/test-proj/services/register",
            json=register_service_payload(run_name="test-run", domain="test-run.gtw.test"),
        )
        assert resp.status_code == 200
        # register 2 replicas
        for job_id in ("xxx-xxx", "yyy-yyy"):
            resp = await client.post(
                "/api/registry/test-proj/services/test-run/replicas/register",
                json=register_replica_payload(job_id=job_id),
            )
            assert resp.status_code == 200
        conf = (tmp_path / "443-test-run.gtw.test.conf").read_text()
        assert "replica xxx-xxx" in conf
        assert "replica yyy-yyy" in conf
        # unregister 1 replica
        resp = await client.post(
            "/api/registry/test-proj/services/test-run/replicas/yyy-yyy/unregister"
        )
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}
        conf = (tmp_path / "443-test-run.gtw.test.conf").read_text()
        assert "replica xxx-xxx" in conf
        assert "replica yyy-yyy" not in conf
        assert system_mocks.reload_nginx.call_count == 4
        assert system_mocks.close_conn.call_count == 1

    async def test_unregister_no_replica_error(self, tmp_path: Path, system_mocks: Mocks) -> None:
        client = make_client(tmp_path)
        # register service
        resp = await client.post(
            "/api/registry/test-proj/services/register",
            json=register_service_payload(run_name="test-run"),
        )
        assert resp.status_code == 200
        # unregister nonexistent replica
        resp = await client.post(
            "/api/registry/test-proj/services/test-run/replicas/xxx-yyy/unregister"
        )
        assert resp.status_code == 400
        assert resp.json() == {
            "detail": (
                "Replica xxx-yyy does not exist in service test-proj/test-run, cannot unregister"
            )
        }
        assert system_mocks.reload_nginx.call_count == 1
        assert system_mocks.close_conn.call_count == 0

    async def test_unregister_no_service_error(self, tmp_path: Path, system_mocks: Mocks) -> None:
        client = make_client(tmp_path)
        resp = await client.post(
            "/api/registry/test-proj/services/test-run/replicas/xxx-yyy/unregister"
        )
        assert resp.status_code == 400
        assert resp.json() == {
            "detail": "Service test-proj/test-run does not exist, cannot unregister replica"
        }
        assert system_mocks.reload_nginx.call_count == 0
        assert system_mocks.close_conn.call_count == 0


@pytest.mark.asyncio
class TestRegisterEntrypoint:
    async def test_register(self, tmp_path: Path, system_mocks: Mocks) -> None:
        client = make_client(tmp_path)
        resp = await client.post(
            "/api/registry/test-proj/entrypoints/register",
            json={"domain": "gateway.gtw.test", "https": False},
        )
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}
        conf = (tmp_path / "443-gateway.gtw.test.conf").read_text()
        assert "proxy_pass http://localhost:8000/api/models/test-proj/;" in conf
        assert "listen 80;" in conf
        assert "listen 443" not in conf
        assert system_mocks.reload_nginx.call_count == 1
        assert system_mocks.run_certbot.call_count == 0

    async def test_register_with_https(self, tmp_path: Path, system_mocks: Mocks) -> None:
        client = make_client(tmp_path)
        resp = await client.post(
            "/api/registry/test-proj/entrypoints/register",
            json={"domain": "gateway.gtw.test", "https": True},
        )
        assert resp.status_code == 200
        conf = (tmp_path / "443-gateway.gtw.test.conf").read_text()
        assert "proxy_pass http://localhost:8000/api/models/test-proj/;" in conf
        assert "listen 80;" in conf
        assert "listen 443 ssl;" in conf
        assert system_mocks.reload_nginx.call_count == 1
        assert system_mocks.run_certbot.call_count == 1
