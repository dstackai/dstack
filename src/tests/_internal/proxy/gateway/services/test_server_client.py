import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

import httpcore2 as httpcore
import httpx2 as httpx
import pytest
from httpcore2._async.connection_pool import AsyncPoolRequest

from dstack._internal.proxy.gateway.services.server_client import HTTPMultiClient

RESPONSE = b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok"


class TestHTTPMultiClientPool:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("failure", ["cancel", "timeout"])
    async def test_reclaims_connection_assigned_to_cancelled_waiter(
        self, tmp_path, monkeypatch, failure
    ):
        backend = httpcore.AsyncMockBackend([RESPONSE])
        queued = asyncio.Event()
        wait_for_connection = AsyncPoolRequest.wait_for_connection

        async def wait(self, timeout=None):
            was_queued = self.connection is None
            if was_queued:
                queued.set()
            connection = await wait_for_connection(self, timeout)
            if was_queued and failure == "timeout":
                # The deadline fires while a connection is assigned, before the
                # waiter resumes. Inject the outcome without waiting on a clock.
                raise httpcore.PoolTimeout()
            return connection

        monkeypatch.setattr(AsyncPoolRequest, "wait_for_connection", wait)
        async with _auth_pool(tmp_path, max_connections=1, network_backend=backend) as pool:
            first = await pool.handle_async_request(
                httpcore.Request("GET", "http://first/", headers={"Host": "first"})
            )
            second = asyncio.create_task(pool.request("GET", "http://second/"))
            await queued.wait()
            # Releasing the only slot assigns a new, unstarted connection to second.
            await first.aclose()
            assert len(pool.connections) == 1
            assert not pool.connections[0].is_connected()
            if failure == "cancel":
                second.cancel()
            with pytest.raises(
                asyncio.CancelledError if failure == "cancel" else httpcore.PoolTimeout
            ):
                await second

            assert not pool._requests
            assert pool.connections == []
            response = await pool.request("GET", "http://next/")
            assert response.status == 200
            assert response.content == b"ok"

    @pytest.mark.asyncio
    async def test_assigns_reclaimed_slot_to_queued_waiter(self, tmp_path, monkeypatch):
        backend = httpcore.AsyncMockBackend([RESPONSE])
        queued = {host: asyncio.Event() for host in (b"cancelled", b"survivor")}
        waiting = {}
        wait_for_connection = AsyncPoolRequest.wait_for_connection

        async def wait(self, timeout=None):
            host = self.request.url.host
            if self.connection is None and host in queued:
                waiting[host] = self
                queued[host].set()
            return await wait_for_connection(self, timeout)

        monkeypatch.setattr(AsyncPoolRequest, "wait_for_connection", wait)
        async with _auth_pool(tmp_path, max_connections=1, network_backend=backend) as pool:
            first = await pool.handle_async_request(
                httpcore.Request("GET", "http://first/", headers={"Host": "first"})
            )
            cancelled = asyncio.create_task(pool.request("GET", "http://cancelled/"))
            survivor = asyncio.create_task(pool.request("GET", "http://survivor/"))
            try:
                await queued[b"cancelled"].wait()
                await queued[b"survivor"].wait()
                await first.aclose()
                cancelled.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await cancelled
                # Reclaiming the abandoned slot must wake the existing waiter without
                # requiring another incoming request to trigger pool maintenance.
                assert waiting[b"survivor"].connection is not None
                response = await survivor
                assert response.status == 200
                assert response.content == b"ok"
            finally:
                cancelled.cancel()
                survivor.cancel()
                await asyncio.gather(cancelled, survivor, return_exceptions=True)

    @pytest.mark.asyncio
    async def test_preserves_connections_being_established(self, tmp_path, monkeypatch):
        backend = httpcore.AsyncMockBackend([RESPONSE])
        connecting = asyncio.Event()
        release_connection = asyncio.Event()
        connect_unix_socket = backend.connect_unix_socket

        async def connect(*args, **kwargs):
            if not connecting.is_set():
                connecting.set()
                await release_connection.wait()
            else:
                raise httpcore.ConnectError("simulated connection failure")
            return await connect_unix_socket(*args, **kwargs)

        monkeypatch.setattr(backend, "connect_unix_socket", connect)
        async with _auth_pool(tmp_path, max_connections=2, network_backend=backend) as pool:
            first = asyncio.create_task(pool.request("GET", "http://first/"))
            try:
                await connecting.wait()
                connection = pool.connections[0]
                assert not connection.is_connected()
                # A failed request triggers cleanup while the first still owns its slot.
                with pytest.raises(httpcore.ConnectError):
                    await pool.request("GET", "http://second/")
                assert connection in pool.connections
                assert not first.done()
                release_connection.set()
                response = await first
                assert response.status == 200
                assert response.content == b"ok"
            finally:
                first.cancel()
                await asyncio.gather(first, return_exceptions=True)

    @pytest.mark.asyncio
    async def test_preserves_connections_with_unread_response_streams(self, tmp_path, monkeypatch):
        backend = httpcore.AsyncMockBackend([RESPONSE])
        connect_unix_socket = backend.connect_unix_socket

        connected = False

        async def connect(*args, **kwargs):
            nonlocal connected
            if connected:
                raise httpcore.ConnectError("simulated connection failure")
            connected = True
            return await connect_unix_socket(*args, **kwargs)

        monkeypatch.setattr(backend, "connect_unix_socket", connect)
        async with _auth_pool(tmp_path, max_connections=2, network_backend=backend) as pool:
            first = await pool.handle_async_request(
                httpcore.Request("GET", "http://first/", headers={"Host": "first"})
            )
            with pytest.raises(httpcore.ConnectError):
                await pool.request("GET", "http://second/")
            # Failed-request cleanup must not close the first response's connection.
            assert await first.aread() == b"ok"
            await first.aclose()

    @pytest.mark.asyncio
    async def test_reuses_idle_connections(self, tmp_path):
        backend = httpcore.AsyncMockBackend([RESPONSE, RESPONSE])
        async with _auth_pool(tmp_path, network_backend=backend) as pool:
            await pool.request("GET", "http://dstack/")
            connection = pool.connections[0]
            response = await pool.request("GET", "http://dstack/")
            assert response.content == b"ok"
            assert pool.connections == [connection]


class TestHTTPMultiClient:
    @pytest.mark.asyncio
    async def test_default_limits_timeouts_and_request(self, tmp_path):
        socket = tmp_path / "server.sock"
        socket.touch()
        client = HTTPMultiClient(tmp_path)
        cached = next(client._iter_clients_rand())
        pool = cached.client._transport._pool
        assert isinstance(pool, httpcore.AsyncConnectionPool)
        assert pool._uds == str(socket)
        assert (pool._max_connections, pool._max_keepalive_connections) == (100, 20)
        assert pool._keepalive_expiry == 5.0
        assert cached.client.timeout == httpx.Timeout(5.0)
        pool._network_backend = httpcore.AsyncMockBackend([RESPONSE])
        try:
            response = await client.post("/api/projects/test/get")
            assert response.status_code == 200
            assert response.text == "ok"
        finally:
            await cached.client.aclose()
            await client.aclose()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("outcome", ["connect_error", "timeout", "forbidden"])
    async def test_failover_uses_httpx2_errors_and_preserves_http_responses(
        self, tmp_path, monkeypatch, outcome
    ):
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

    @pytest.mark.asyncio
    async def test_sends_authorization_over_unix_socket(self):
        # Real local I/O verifies the migrated transport's UDS support and headers;
        # the deterministic pool tests above use mock I/O to force cancellation races.
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


@asynccontextmanager
async def _auth_pool(tmp_path, **settings):
    # Exercise the pool created by the actual gateway transport. Lower capacity
    # and mocked I/O make the production cancellation race deterministic and fast.
    info = HTTPMultiClient._make_client(tmp_path / "server.sock")
    async with info.client:
        pool = info.client._transport._pool
        assert isinstance(pool, httpcore.AsyncConnectionPool)
        for key, value in settings.items():
            setattr(pool, f"_{key}", value)
        yield pool
