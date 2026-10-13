from unittest.mock import AsyncMock

import httpx2 as httpx
import pytest
import pytest_asyncio
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from dstack._internal.proxy.gateway.auth import GatewayProxyAuthProvider
from dstack._internal.proxy.gateway.services.server_client import HTTPMultiClient
from dstack._internal.proxy.lib.errors import UnexpectedProxyError


@pytest_asyncio.fixture(autouse=True)
async def clear_auth_cache():
    cache = GatewayProxyAuthProvider.is_project_member.cache
    await cache.clear()
    yield
    await cache.clear()


@pytest.mark.asyncio
class TestGatewayProxyAuthProvider:
    @pytest.mark.parametrize("status", [200, 403])
    async def test_caches_project_token_decision_for_sixty_seconds(self, monkeypatch, status):
        requests = []

        def handle(request):
            requests.append(request)
            return httpx.Response(status)

        cache = GatewayProxyAuthProvider.is_project_member.cache
        set_value = AsyncMock(wraps=cache.set)
        monkeypatch.setattr(cache, "set", set_value)
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

    async def test_propagates_trace_context_to_server(self, monkeypatch):
        exporter = InMemorySpanExporter()
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        # A local provider, as the global one can only be set once per process
        monkeypatch.setattr(trace, "get_tracer", provider.get_tracer)
        requests = []

        def handle(request):
            requests.append(request)
            return httpx.Response(403)

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handle), base_url="http://dstack/"
        ) as client:
            assert await GatewayProxyAuthProvider(client).is_project_member("main", "t") is False

        (span,) = exporter.get_finished_spans()
        assert span.attributes is not None
        assert span.attributes["dstack.project.name"] == "main"
        assert span.attributes["http.response.status_code"] == 403
        assert f"{span.context.trace_id:032x}" in requests[0].headers["traceparent"]

    @pytest.mark.parametrize("failure", [500, httpx.ReadTimeout])
    async def test_httpx2_failures_are_wrapped_and_not_cached(self, failure):
        requests = 0

        def handle(request):
            nonlocal requests
            requests += 1
            if requests > 1:
                return httpx.Response(200)
            if isinstance(failure, int):
                return httpx.Response(failure)
            raise failure("temporary failure", request=request)

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handle), base_url="http://dstack/"
        ) as client:
            provider = GatewayProxyAuthProvider(client)
            with pytest.raises(UnexpectedProxyError) as exc:
                await provider.is_project_member("test", "token")
            assert isinstance(exc.value.__cause__, httpx.HTTPError)
            assert await provider.is_project_member("test", "token")
            assert requests == 2

    async def test_no_servers_reaches_auth_error_boundary(self, tmp_path):
        async with HTTPMultiClient(tmp_path) as client:
            provider = GatewayProxyAuthProvider(client)
            with pytest.raises(UnexpectedProxyError) as exc:
                await provider.is_project_member("test", "token")
            assert isinstance(exc.value.__cause__, httpx.RequestError)
            assert exc.value.__cause__.request.url.path == "/api/projects/test/get"
