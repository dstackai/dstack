from typing import AsyncGenerator, Generator, Tuple
from unittest.mock import patch

import httpx
import pytest
from fastapi import FastAPI

from dstack._internal.proxy.deps import BaseProxyDependencyInjector
from dstack._internal.proxy.repos.base import BaseProxyRepo, Project, Replica, Service
from dstack._internal.proxy.routers.service_proxy import router
from dstack._internal.proxy.testing.repo import ProxyTestRepo


def make_app(repo: BaseProxyRepo) -> FastAPI:
    class DependencyInjector(BaseProxyDependencyInjector):
        async def get_repo(self) -> AsyncGenerator[BaseProxyRepo, None]:
            yield repo

    app = FastAPI()
    app.state.proxy_dependency_injector = DependencyInjector()
    app.include_router(router, prefix="/services")
    return app


def make_client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app))


def make_app_client(repo: BaseProxyRepo) -> Tuple[FastAPI, httpx.AsyncClient]:
    app = make_app(repo)
    client = make_client(app)
    return app, client


def make_project(name: str) -> Project:
    return Project(name=name, ssh_private_key="secret")


def make_service(run_name: str, auth: bool = False) -> Service:
    return Service(
        id="xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
        run_name=run_name,
        auth=auth,
        app_port=80,
        replicas=[
            Replica(
                id="xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
                ssh_destination="ubuntu@server",
                ssh_port=22,
                ssh_proxy=None,
            )
        ],
    )


MOCK_REPLICA_CLIENT_TIMEOUT = 8


@pytest.fixture
def mock_replica_client_httpbin(httpbin) -> Generator[None, None, None]:
    with patch(
        "dstack._internal.proxy.services.service_proxy.get_replica_client"
    ) as get_replica_client_mock:
        get_replica_client_mock.return_value = httpx.AsyncClient(
            base_url=httpbin.url, timeout=MOCK_REPLICA_CLIENT_TIMEOUT
        )
        yield


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["get", "post", "put", "patch", "delete"])
async def test_proxy(mock_replica_client_httpbin, method: str) -> None:
    methods_without_body = "get", "delete"
    repo = ProxyTestRepo()
    await repo.add_project(make_project("test-proj"))
    await repo.add_service(project_name="test-proj", service=make_service("httpbin"))
    _, client = make_app_client(repo)
    req_body = "." * 20 * 2**20 if method not in methods_without_body else None
    resp = await client.request(
        method,
        f"http://test-host:8888/services/test-proj/httpbin/{method}?a=b&c=",
        headers={"User-Agent": "test-ua", "Connection": "keep-alive"},
        content=req_body,
    )
    assert resp.status_code == 200
    assert resp.headers["server"].startswith("Pytest-HTTPBIN")
    resp_body = resp.json()
    assert resp_body["url"] == f"http://test-host:8888/{method}?a=b&c="
    assert resp_body["args"] == {"a": "b", "c": ""}
    assert resp_body["headers"]["Host"] == "test-host:8888"
    assert resp_body["headers"]["User-Agent"] == "test-ua"
    assert resp_body["headers"]["Connection"] == "keep-alive"
    if method not in methods_without_body:
        assert resp_body["data"] == req_body


@pytest.mark.asyncio
async def test_proxy_method_head(mock_replica_client_httpbin) -> None:
    repo = ProxyTestRepo()
    await repo.add_project(make_project("test-proj"))
    await repo.add_service(project_name="test-proj", service=make_service("httpbin"))
    _, client = make_app_client(repo)
    url = "http://test-host/services/test-proj/httpbin/"
    get_resp = await client.get(url)
    head_resp = await client.head(url)
    assert get_resp.status_code == head_resp.status_code == 200
    assert head_resp.headers["Content-Length"] == get_resp.headers["Content-Length"]
    assert int(head_resp.headers["Content-Length"]) > 0
    assert head_resp.content == b""


@pytest.mark.asyncio
async def test_proxy_method_options(mock_replica_client_httpbin) -> None:
    repo = ProxyTestRepo()
    await repo.add_project(make_project("test-proj"))
    await repo.add_service(project_name="test-proj", service=make_service("httpbin"))
    _, client = make_app_client(repo)
    resp = await client.options("http://test-host/services/test-proj/httpbin/get")
    assert resp.status_code == 200
    assert set(resp.headers["Allow"].split(", ")) == {"HEAD", "GET", "OPTIONS"}
    assert resp.content == b""


@pytest.mark.asyncio
@pytest.mark.parametrize("code", [204, 304, 418, 503])
async def test_proxy_status_codes(mock_replica_client_httpbin, code: int) -> None:
    repo = ProxyTestRepo()
    await repo.add_project(make_project("test-proj"))
    await repo.add_service(project_name="test-proj", service=make_service("httpbin"))
    _, client = make_app_client(repo)
    resp = await client.get(f"http://test-host/services/test-proj/httpbin/status/{code}")
    assert resp.status_code == code


@pytest.mark.asyncio
async def test_proxy_not_leaks_cookies(mock_replica_client_httpbin) -> None:
    repo = ProxyTestRepo()
    await repo.add_project(make_project("test-proj"))
    await repo.add_service(project_name="test-proj", service=make_service("httpbin"))
    app = make_app(repo)
    client1 = make_client(app)
    client2 = make_client(app)
    cookies_url = "http://test-host/services/test-proj/httpbin/cookies"
    await client1.get(cookies_url + "/set?a=1")
    await client1.get(cookies_url + "/set?b=2")
    await client2.get(cookies_url + "/set?a=3")
    resp1 = await client1.get(cookies_url)
    resp2 = await client2.get(cookies_url)
    assert resp1.json()["cookies"] == {"a": "1", "b": "2"}
    assert resp2.json()["cookies"] == {"a": "3"}


@pytest.mark.asyncio
async def test_proxy_gateway_timeout(mock_replica_client_httpbin) -> None:
    repo = ProxyTestRepo()
    await repo.add_project(make_project("test-proj"))
    await repo.add_service(project_name="test-proj", service=make_service("httpbin"))
    _, client = make_app_client(repo)
    assert MOCK_REPLICA_CLIENT_TIMEOUT < 10
    resp = await client.get("http://test-host/services/test-proj/httpbin/delay/10")
    assert resp.status_code == 504
    assert resp.json()["detail"] == "Gateway Timeout"


@pytest.mark.asyncio
async def test_proxy_run_not_found(mock_replica_client_httpbin) -> None:
    repo = ProxyTestRepo()
    await repo.add_project(make_project("test-proj"))
    await repo.add_service(project_name="test-proj", service=make_service("test-run"))
    _, client = make_app_client(repo)
    resp = await client.get("http://test-host/services/test-proj/unknown/")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Service test-proj/unknown not found"


@pytest.mark.asyncio
async def test_proxy_project_not_found(mock_replica_client_httpbin) -> None:
    _, client = make_app_client(ProxyTestRepo())
    resp = await client.get("http://test-host/services/unknown/test-run/")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Service unknown/test-run not found"


@pytest.mark.asyncio
async def test_redirect_to_service_root(mock_replica_client_httpbin) -> None:
    repo = ProxyTestRepo()
    await repo.add_project(make_project("test-proj"))
    await repo.add_service(project_name="test-proj", service=make_service("httpbin"))
    _, client = make_app_client(repo)
    url = "http://test-host/services/test-proj/httpbin"
    resp = await client.get(url, follow_redirects=False)
    assert resp.status_code == 308
    assert resp.headers["Location"] == url + "/"
    resp = await client.get(url, follow_redirects=True)
    assert resp.status_code == 200
    assert resp.request.url == url + "/"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("token", "status"), [("correct-token", 200), ("incorrect-token", 403), ("", 403), (None, 403)]
)
async def test_auth(mock_replica_client_httpbin, token: str, status: int) -> None:
    repo = ProxyTestRepo(project_to_tokens={"test-proj": {"correct-token"}})
    await repo.add_project(make_project("test-proj"))
    await repo.add_service(project_name="test-proj", service=make_service("httpbin", auth=True))
    _, client = make_app_client(repo)
    url = "http://test-host/services/test-proj/httpbin/"
    headers = {}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    resp = await client.get(url, headers=headers)
    assert resp.status_code == status
