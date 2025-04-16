import re
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx
import pytest
from freezegun import freeze_time

from dstack._internal.core.errors import SSHError
from dstack._internal.proxy.gateway.app import make_app
from dstack._internal.proxy.gateway.repo.repo import GatewayProxyRepo
from dstack._internal.proxy.gateway.services.nginx import Nginx
from dstack._internal.proxy.gateway.testing.common import Mocks
from dstack._internal.proxy.lib.models import ChatModel, OpenAIChatModelFormat


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
    rate_limits: Optional[list[dict]] = None,
) -> dict:
    return {
        "run_name": run_name,
        "domain": domain,
        "https": https,
        "auth": auth,
        "client_max_body_size": client_max_body_size,
        "options": options or {},
        "rate_limits": rate_limits or [],
        "ssh_private_key": "private-key",
    }


def register_replica_payload(job_id: str = "xxx-xxx") -> dict:
    return {
        "job_id": job_id,
        "app_port": 8888,
        "ssh_host": "host.test",
        "ssh_port": 22,
        "ssh_proxy": None,
        "ssh_head_proxy": None,
        "ssh_head_proxy_private_key": None,
    }


def register_replica_payload_with_head_proxy(job_id: str = "xxx-xxx") -> dict:
    return {
        "job_id": job_id,
        "app_port": 8888,
        "ssh_host": "host.test",
        "ssh_port": 22,
        "ssh_proxy": None,
        "ssh_head_proxy": {
            "hostname": "proxy.test",
            "username": "debian",
            "port": 222,
        },
        "ssh_head_proxy_private_key": "private-key",
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
        assert "auth_request /_dstack_auth;" not in conf
        # no replicas
        assert "upstream" not in conf
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
        assert "auth_request /_dstack_auth;" in conf
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

    async def test_register_with_rate_limits(self, tmp_path: Path, system_mocks: Mocks) -> None:
        client = make_client(tmp_path)
        resp = await client.post(
            "/api/registry/test-proj/services/register",
            json=register_service_payload(
                domain="test-run.gtw.test",
                rate_limits=[
                    {
                        "prefix": "/a",
                        "key": {"type": "ip_address"},
                        "rps": 2.5,
                        "burst": 5,
                    },
                    {
                        "prefix": "/b",
                        "key": {"type": "header", "header": "X-Api-Key"},
                        "rps": 1,
                        "burst": 0,
                    },
                ],
            ),
        )
        assert resp.status_code == 200
        conf = (tmp_path / "443-test-run.gtw.test.conf").read_text()
        assert (
            "limit_req_zone $binary_remote_addr zone=0.test-run.gtw.test:10m rate=150r/m;" in conf
        )
        assert "limit_req_zone $http_x_api_key zone=1.test-run.gtw.test:10m rate=60r/m;" in conf
        assert "location /a {" in conf
        assert "location /b {" in conf
        assert "location / {" in conf
        assert "limit_req zone=0.test-run.gtw.test burst=5 nodelay;" in conf
        assert "limit_req zone=1.test-run.gtw.test;" in conf

    async def test_register_with_root_rate_limit(
        self, tmp_path: Path, system_mocks: Mocks
    ) -> None:
        client = make_client(tmp_path)
        resp = await client.post(
            "/api/registry/test-proj/services/register",
            json=register_service_payload(
                domain="test-run.gtw.test",
                rate_limits=[
                    {"prefix": "/", "key": {"type": "ip_address"}, "rps": 1, "burst": 1},
                ],
            ),
        )
        assert resp.status_code == 200
        conf = (tmp_path / "443-test-run.gtw.test.conf").read_text()
        assert (
            "limit_req_zone $binary_remote_addr zone=0.test-run.gtw.test:10m rate=60r/m;" in conf
        )
        assert "location / {" in conf
        assert "limit_req zone=0.test-run.gtw.test burst=1 nodelay;" in conf

    async def test_register_without_rate_limits(self, tmp_path: Path, system_mocks: Mocks) -> None:
        client = make_client(tmp_path)
        resp = await client.post(
            "/api/registry/test-proj/services/register",
            json=register_service_payload(domain="test-run.gtw.test", rate_limits=[]),
        )
        assert resp.status_code == 200
        conf = (tmp_path / "443-test-run.gtw.test.conf").read_text()
        assert "limit_req_zone" not in conf
        assert "limit_req zone=" not in conf
        assert "location / {" in conf


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
        assert "upstream" not in conf
        # register 2 replicas
        resp = await client.post(
            "/api/registry/test-proj/services/test-run/replicas/register",
            json=register_replica_payload(job_id="xxx-xxx"),
        )
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}
        resp = await client.post(
            "/api/registry/test-proj/services/test-run/replicas/register",
            json=register_replica_payload_with_head_proxy(job_id="yyy-yyy"),
        )
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}
        conf = (tmp_path / "443-test-run.gtw.test.conf").read_text()
        assert "upstream test-run.gtw.test.upstream" in conf
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

    async def test_register_twice_error(self, tmp_path: Path, system_mocks: Mocks) -> None:
        client = make_client(tmp_path)
        # register service
        resp = await client.post(
            "/api/registry/test-proj/services/register",
            json=register_service_payload(run_name="test-run", domain="test-run.gtw.test"),
        )
        assert resp.status_code == 200
        # register replica
        resp = await client.post(
            "/api/registry/test-proj/services/test-run/replicas/register",
            json=register_replica_payload(job_id="aaa-aaa"),
        )
        assert resp.status_code == 200
        # register the same replica
        resp = await client.post(
            "/api/registry/test-proj/services/test-run/replicas/register",
            json=register_replica_payload(job_id="aaa-aaa"),
        )
        assert resp.status_code == 400
        assert resp.json() == {
            "detail": "Replica aaa-aaa already exists in service test-proj/test-run"
        }
        assert system_mocks.reload_nginx.call_count == 2
        assert system_mocks.open_conn.call_count == 1

    async def test_register_connection_error(self, tmp_path: Path, system_mocks: Mocks) -> None:
        client = make_client(tmp_path)
        # register service
        resp = await client.post(
            "/api/registry/test-proj/services/register",
            json=register_service_payload(run_name="test-run", domain="test-run.gtw.test"),
        )
        assert resp.status_code == 200
        conf_before = (tmp_path / "443-test-run.gtw.test.conf").read_text()
        # register invalid replica
        system_mocks.open_conn.side_effect = SSHError("test error")
        resp = await client.post(
            "/api/registry/test-proj/services/test-run/replicas/register",
            json=register_replica_payload(job_id="abc-def"),
        )
        assert resp.status_code == 400
        assert resp.json() == {
            "detail": "Cannot register replica abc-def in service test-proj/test-run: test error"
        }
        conf_after = (tmp_path / "443-test-run.gtw.test.conf").read_text()
        assert conf_after == conf_before


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
