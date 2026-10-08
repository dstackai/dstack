from unittest.mock import AsyncMock

import httpx2 as httpx
import pytest
import pytest_asyncio

from dstack._internal.proxy.gateway.auth import GatewayProxyAuthProvider
from dstack._internal.proxy.gateway.services.server_client import HTTPMultiClient
from dstack._internal.proxy.lib.errors import UnexpectedProxyError


@pytest_asyncio.fixture(autouse=True)
async def clear_auth_cache():
    cache = GatewayProxyAuthProvider.is_project_member.cache
    await cache.clear()
    yield
    await cache.clear()


class TestGatewayProxyAuthProvider:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("status", [200, 403])
    async def test_caches_project_token_decision_for_sixty_seconds(self, monkeypatch, status):
        requests = []

        def handle(request):
            requests.append(request)
            return httpx.Response(status)

        cache = GatewayProxyAuthProvider.is_project_member.cache
        set_value = AsyncMock(wraps=cache._set)
        monkeypatch.setattr(cache, "_set", set_value)
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handle), base_url="http://dstack/"
        ) as client:
            provider = GatewayProxyAuthProvider(client)
            for _ in range(2):
                assert await provider.is_project_member("first", "token") is (status == 200)
            assert len(requests) == 1
            assert requests[0].method == "POST"
            assert requests[0].url.path == "/api/projects/first/get"
            assert requests[0].headers["Authorization"] == "Bearer token"
            assert set_value.call_args.kwargs["ttl"] == 60

            # Different tokens and projects must not inherit another cached decision.
            await provider.is_project_member("first", "other-token")
            await provider.is_project_member("second", "token")
            assert len(requests) == 3

            # Eviction must cause a fresh check, without waiting for the real clock.
            await cache.clear()
            await provider.is_project_member("first", "token")
            assert len(requests) == 4

    @pytest.mark.asyncio
    @pytest.mark.parametrize("failure", [500, 429, httpx.ConnectError, httpx.ReadTimeout])
    async def test_httpx2_failures_are_wrapped_and_not_cached(self, failure):
        requests = 0

        def handle(request):
            nonlocal requests
            requests += 1
            if requests > 2:
                return httpx.Response(200)
            if isinstance(failure, int):
                return httpx.Response(failure)
            raise failure("temporary failure", request=request)

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handle), base_url="http://dstack/"
        ) as client:
            provider = GatewayProxyAuthProvider(client)
            for _ in range(2):
                with pytest.raises(UnexpectedProxyError) as exc:
                    await provider.is_project_member("test", "token")
                assert isinstance(exc.value.__cause__, httpx.HTTPError)
            assert await provider.is_project_member("test", "token")
            assert await provider.is_project_member("test", "token")
            assert requests == 3

    @pytest.mark.asyncio
    @pytest.mark.parametrize("failure", [None, httpx.ConnectError, httpx.PoolTimeout])
    async def test_all_server_failures_reach_auth_error_boundary(self, tmp_path, failure):
        client = HTTPMultiClient(tmp_path)
        if failure is not None:
            (tmp_path / "server.sock").touch()
        cached = list(client._iter_clients_rand())

        def fail(request):
            raise failure("server unavailable", request=request)

        for info in cached:
            await info.client.aclose()
            info.client = httpx.AsyncClient(transport=httpx.MockTransport(fail))
        try:
            provider = GatewayProxyAuthProvider(client)
            with pytest.raises(UnexpectedProxyError) as exc:
                await provider.is_project_member("test", "token")
            assert isinstance(exc.value.__cause__, httpx.RequestError)
            assert exc.value.__cause__.request.url.path == "/api/projects/test/get"
        finally:
            for info in cached:
                await info.client.aclose()
            await client.aclose()
