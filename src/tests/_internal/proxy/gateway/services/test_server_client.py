import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory

import httpcore2 as httpcore
import httpx2 as httpx
import pytest
from httpcore2._async.connection_pool import AsyncPoolRequest

from dstack._internal.proxy.gateway.services.server_client import HTTPMultiClient

RESPONSE = b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok"


@pytest.mark.asyncio
class TestHTTPMultiClient:
    @pytest.mark.parametrize("failure", ["cancel", "timeout"])
    async def test_recovers_after_cancelled_pool_waiter(self, tmp_path, monkeypatch, failure):
        (tmp_path / "server.sock").touch()
        client = HTTPMultiClient(tmp_path)
        cached = next(client._iter_clients_rand())
        pool = cached.client._transport._pool
        assert isinstance(pool, httpcore.AsyncConnectionPool)
        pool._max_connections = 1
        # Closing the first response assigns a fresh connection to the queued request.
        pool._network_backend = httpcore.AsyncMockBackend(
            [RESPONSE.replace(b"Content-Length", b"Connection: close\r\nContent-Length")]
        )
        queued = asyncio.Event()
        wait_for_connection = AsyncPoolRequest.wait_for_connection

        async def wait(self, timeout=None):
            was_queued = self.connection is None
            if was_queued:
                queued.set()
            connection = await wait_for_connection(self, timeout)
            if was_queued and failure == "timeout":
                # Force the original race without waiting on a real deadline: the
                # waiter expires after assignment, before starting its connection.
                raise httpcore.PoolTimeout()
            return connection

        monkeypatch.setattr(AsyncPoolRequest, "wait_for_connection", wait)
        second = None
        try:
            first = await client.send(
                client.build_request("POST", "/api/projects/test/get"), stream=True
            )
            second = asyncio.create_task(client.post("/api/projects/test/get"))
            await asyncio.wait_for(queued.wait(), timeout=1)
            await first.aclose()
            if failure == "cancel":
                second.cancel()
            with pytest.raises(
                asyncio.CancelledError if failure == "cancel" else httpx.RequestError
            ):
                await second

            # The abandoned connection must not permanently consume the only slot.
            assert pool.connections == []
            response = await client.post("/api/projects/test/get")
            assert response.status_code == 200
            assert response.text == "ok"
        finally:
            if second is not None:
                second.cancel()
                await asyncio.gather(second, return_exceptions=True)
            await cached.client.aclose()
            await client.aclose()

    @pytest.mark.parametrize("outcome", ["connect_error", "timeout", "forbidden"])
    async def test_failover_preserves_http_responses(self, tmp_path, monkeypatch, outcome):
        for name in ("a.sock", "b.sock"):
            (tmp_path / name).touch()
        monkeypatch.setattr("random.shuffle", lambda sockets: sockets.sort())
        client = HTTPMultiClient(tmp_path)
        cached = list(client._iter_clients_rand())
        requests = []

        def first(request):
            requests.append("first")
            if outcome == "connect_error":
                raise httpx.ConnectError("disconnected", request=request)
            if outcome == "timeout":
                raise httpx.PoolTimeout("busy", request=request)
            return httpx.Response(403)

        def second(request):
            requests.append("second")
            return httpx.Response(200)

        for info, handler in zip(cached, (first, second)):
            await info.client.aclose()
            info.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        try:
            response = await client.post("/api/projects/test/get")
            assert response.status_code == (403 if outcome == "forbidden" else 200)
            assert requests == (["first"] if outcome == "forbidden" else ["first", "second"])
        finally:
            for info in cached:
                await info.client.aclose()
            await client.aclose()

    async def test_sends_authorization_over_unix_socket(self):
        # Real local I/O verifies the migrated transport's UDS support and headers.
        headers = []

        async def handle(reader, writer):
            try:
                headers.append(await reader.readuntil(b"\r\n\r\n"))
                writer.write(RESPONSE)
                await writer.drain()
            finally:
                writer.close()
                await writer.wait_closed()

        # A short path is needed for macOS's Unix-socket pathname limit.
        with TemporaryDirectory() as directory:
            socket = Path(directory) / "server.sock"
            server = await asyncio.start_unix_server(handle, path=socket)
            client = HTTPMultiClient(Path(directory))
            try:
                response = await client.post(
                    "/api/projects/test/get", headers={"Authorization": "Bearer test-token"}
                )
                assert response.status_code == 200
                assert b"POST /api/projects/test/get HTTP/1.1\r\n" in headers[0]
                assert b"Authorization: Bearer test-token\r\n" in headers[0]
            finally:
                for info in client._clients_cache.values():
                    await info.client.aclose()
                await client.aclose()
                server.close()
                await server.wait_closed()
