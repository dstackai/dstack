import asyncio
from pathlib import Path

import httpcore
import pytest
from httpcore._async.connection_pool import AsyncPoolRequest

from dstack._internal.proxy.gateway.services.server_client import (
    HTTPMultiClient,
    _ServerConnectionPool,
    _ServerTransport,
)

RESPONSE = b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok"


class TestServerConnectionPool:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("failure", ["cancel", "timeout"])
    async def test_reclaims_connection_assigned_to_cancelled_waiter(self, monkeypatch, failure):
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
        async with _ServerConnectionPool(max_connections=1, network_backend=backend) as pool:
            first = await pool.handle_async_request(
                httpcore.Request("GET", "http://first/", headers={"Host": "first"})
            )
            second = asyncio.create_task(pool.request("GET", "http://second/"))
            await queued.wait()
            # Releasing the only slot assigns a new, unstarted connection to second.
            await first.aclose()
            assert len(pool.connections) == 1
            assert pool.connections[0].info() == "CONNECTING"
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
    async def test_assigns_reclaimed_slot_to_queued_waiter(self, monkeypatch):
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
        async with _ServerConnectionPool(max_connections=1, network_backend=backend) as pool:
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
    async def test_preserves_connections_being_established(self, monkeypatch):
        backend = httpcore.AsyncMockBackend([RESPONSE])
        connecting = asyncio.Event()
        release_connection = asyncio.Event()
        connect_tcp = backend.connect_tcp

        async def connect(host, *args, **kwargs):
            if host == "first":
                connecting.set()
                await release_connection.wait()
            else:
                raise httpcore.ConnectError("simulated connection failure")
            return await connect_tcp(host, *args, **kwargs)

        monkeypatch.setattr(backend, "connect_tcp", connect)
        async with _ServerConnectionPool(max_connections=2, network_backend=backend) as pool:
            first = asyncio.create_task(pool.request("GET", "http://first/"))
            try:
                await connecting.wait()
                connection = pool.connections[0]
                assert connection.info() == "CONNECTING"
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
    async def test_preserves_connections_with_unread_response_streams(self, monkeypatch):
        backend = httpcore.AsyncMockBackend([RESPONSE])
        connect_tcp = backend.connect_tcp

        async def connect(host, *args, **kwargs):
            if host == "second":
                raise httpcore.ConnectError("simulated connection failure")
            return await connect_tcp(host, *args, **kwargs)

        monkeypatch.setattr(backend, "connect_tcp", connect)
        async with _ServerConnectionPool(max_connections=2, network_backend=backend) as pool:
            first = await pool.handle_async_request(
                httpcore.Request("GET", "http://first/", headers={"Host": "first"})
            )
            with pytest.raises(httpcore.ConnectError):
                await pool.request("GET", "http://second/")
            # Failed-request cleanup must not close the first response's connection.
            assert await first.aread() == b"ok"
            await first.aclose()

    @pytest.mark.asyncio
    async def test_reuses_idle_connections(self):
        backend = httpcore.AsyncMockBackend([RESPONSE, RESPONSE])
        async with _ServerConnectionPool(network_backend=backend) as pool:
            await pool.request("GET", "http://dstack/")
            connection = pool.connections[0]
            response = await pool.request("GET", "http://dstack/")
            assert response.content == b"ok"
            assert pool.connections == [connection]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("http2", [False, True])
    async def test_single_waiter_reuses_first_match_without_scanning_later_connections(
        self, monkeypatch, http2
    ):
        async with _ServerConnectionPool(
            max_connections=3,
            max_keepalive_connections=3,
            http2=http2,
            network_backend=httpcore.AsyncMockBackend([RESPONSE]),
        ) as pool:
            scheme = "https" if http2 else "http"
            requests = [
                httpcore.Request("GET", f"{scheme}://{host}/", headers={"Host": host})
                for host in ("other", "dstack", "dstack")
            ]
            if http2:
                # HTTPS HTTP/2 connections can be shared while still connecting;
                # reusing them must not depend on the connection being idle.
                pool._connections = [
                    pool.create_connection(request.url.origin) for request in requests
                ]
                assert all(not connection.is_idle() for connection in pool.connections)
            else:
                responses = [await pool.handle_async_request(request) for request in requests]
                for response in responses:
                    assert await response.aread() == b"ok"
                    await response.aclose()
                assert all(connection.is_idle() for connection in pool.connections)
            different_origin, first_match, later_match = pool.connections
            assert not different_origin.can_handle_request(requests[1].url.origin)

            def unexpected_scan(*args):
                pytest.fail("A single waiter must stop scanning after its first reusable match")

            monkeypatch.setattr(later_match, "can_handle_request", unexpected_scan)
            monkeypatch.setattr(later_match, "is_available", unexpected_scan)
            waiter = AsyncPoolRequest(requests[1])
            pool._requests.append(waiter)

            assert pool._assign_requests_to_connections() == []
            assert waiter.connection is first_match
            assert pool.connections == [different_origin, first_match, later_match]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("active_request", [False, True])
    @pytest.mark.parametrize("state", ["idle", "excess_idle", "expired", "closed"])
    async def test_response_completion_without_waiters_skips_availability_scan(
        self, monkeypatch, active_request, state
    ):
        async with _ServerConnectionPool(
            max_connections=2,
            max_keepalive_connections=0 if state == "excess_idle" else 2,
            keepalive_expiry=-float("inf") if state == "expired" else 5.0,
            network_backend=httpcore.AsyncMockBackend([RESPONSE]),
        ) as pool:
            responses = [
                await pool.handle_async_request(
                    httpcore.Request("GET", "http://dstack/", headers={"Host": "dstack"})
                )
                for _ in range(1 + active_request)
            ]
            released, *busy = pool.connections

            def is_available():
                pytest.fail(
                    "Response completion must not scan availability without queued requests"
                )

            with monkeypatch.context() as patch:
                for connection in pool.connections:
                    patch.setattr(connection, "is_available", is_available)
                # Closing an unread HTTP/1.1 response closes its connection. Reading
                # it first returns it idle, allowing expiry/keepalive cleanup instead.
                if state != "closed":
                    assert await responses[0].aread() == b"ok"
                await responses[0].aclose()

            if state == "idle":
                assert pool.connections == [released, *busy]
                assert released.is_idle()
            else:
                assert pool.connections == busy
                assert released.is_closed()
            assert len(pool._requests) == active_request
            if active_request:
                assert pool._requests[0].connection is busy[0]
                assert not pool._requests[0].is_queued()
                assert not busy[0].is_closed()
                assert await responses[1].aread() == b"ok"
                await responses[1].aclose()

    @pytest.mark.asyncio
    async def test_saturated_pool_waits_without_scanning_unavailable_connections(
        self, monkeypatch
    ):
        backend = httpcore.AsyncMockBackend([RESPONSE, RESPONSE])
        queued = asyncio.Event()
        wait_for_connection = AsyncPoolRequest.wait_for_connection

        async def wait(self, timeout=None):
            if self.connection is None:
                queued.set()
            return await wait_for_connection(self, timeout)

        monkeypatch.setattr(AsyncPoolRequest, "wait_for_connection", wait)
        async with _ServerConnectionPool(max_connections=1, network_backend=backend) as pool:
            first = await pool.handle_async_request(
                httpcore.Request("GET", "http://dstack/", headers={"Host": "dstack"})
            )
            connection = pool.connections[0]
            can_handle_request = connection.can_handle_request
            scans = 0

            def can_handle(origin):
                nonlocal scans
                scans += 1
                return can_handle_request(origin)

            monkeypatch.setattr(connection, "can_handle_request", can_handle)
            second = asyncio.create_task(pool.request("GET", "http://dstack/"))
            try:
                await queued.wait()
                assert scans == 0
                assert not second.done()
                await first.aread()
                await first.aclose()
                response = await second
                assert response.status == 200
                assert response.content == b"ok"
            finally:
                second.cancel()
                await asyncio.gather(second, return_exceptions=True)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("reuse", [True, False])
    async def test_response_completion_does_not_rescan_busy_connections(self, monkeypatch, reuse):
        async with _ServerConnectionPool(
            max_connections=3,
            max_keepalive_connections=3 if reuse else 1,
            network_backend=httpcore.AsyncMockBackend([RESPONSE]),
        ) as pool:
            responses = [
                await pool.handle_async_request(
                    httpcore.Request("GET", "http://dstack/", headers={"Host": "dstack"})
                )
                for _ in range(3)
            ]
            released, *busy = pool.connections
            scans = 0

            def can_handle(origin):
                nonlocal scans
                scans += 1
                return True

            for connection in busy:
                monkeypatch.setattr(connection, "can_handle_request", can_handle)
            queued = [
                AsyncPoolRequest(httpcore.Request("GET", "http://dstack/")) for _ in range(100)
            ]
            pool._requests.extend(queued)

            await responses[0].aread()
            await responses[0].aclose()

            # A completed response bypasses the all-busy shortcut. Pool maintenance
            # must not rescan busy connections for each of the remaining waiters.
            assert scans <= len(busy)
            if reuse:
                assert all(request.connection is released for request in queued)
            else:
                assert released.is_closed()
                assert queued[0].connection is not None
                assert queued[0].connection is not released
                assert all(request.connection is None for request in queued[1:])
            assert len(pool.connections) == 3

    @pytest.mark.asyncio
    async def test_evicted_connection_is_not_reused_by_later_waiter(self):
        async with _ServerConnectionPool(
            max_connections=1,
            network_backend=httpcore.AsyncMockBackend([RESPONSE]),
        ) as pool:
            await pool.request("GET", "http://first/")
            original = pool.connections[0]
            queued = [
                AsyncPoolRequest(httpcore.Request("GET", f"http://{host}/"))
                for host in ("second", "first")
            ]
            pool._requests.extend(queued)

            closing = pool._assign_requests_to_connections()

            assert closing == [original]
            assert queued[0].connection is pool.connections[0]
            assert queued[0].connection is not original
            assert queued[1].connection is None
            await pool._close_connections(closing)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("state", ["spare_capacity", "idle", "closed", "expired"])
    async def test_assigns_when_capacity_or_connections_are_available(self, state):
        async with _ServerConnectionPool(
            max_connections=2 if state == "spare_capacity" else 1,
            max_keepalive_connections=1,
            network_backend=httpcore.AsyncMockBackend([RESPONSE]),
        ) as pool:
            response = await pool.handle_async_request(
                httpcore.Request("GET", "http://dstack/", headers={"Host": "dstack"})
            )
            connection = pool.connections[0]
            assert isinstance(connection, httpcore.AsyncHTTPConnection)
            if state != "spare_capacity":
                await response.aread()
                await response.aclose()
            if state == "closed":
                await connection.aclose()
            elif state == "expired":
                assert isinstance(connection._connection, httpcore.AsyncHTTP11Connection)
                connection._connection._expire_at = -float("inf")
            queued = [
                AsyncPoolRequest(httpcore.Request("GET", "http://dstack/")) for _ in range(2)
            ]
            pool._requests.extend(queued)
            closing = pool._assign_requests_to_connections()
            assert queued[0].connection is not None
            if state == "idle":
                assert queued[0].connection is connection
            else:
                assert queued[0].connection is not connection
            if state == "expired":
                assert connection in closing
            await pool._close_connections(closing)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("existing_connection", [True, False])
    async def test_assigns_available_http2_connection_to_multiple_requests(
        self, existing_connection
    ):
        async with _ServerConnectionPool(max_connections=1, http2=True) as pool:
            request = httpcore.Request("GET", "https://dstack/")
            if existing_connection:
                connection = pool.create_connection(request.url.origin)
                pool._connections.append(connection)
                assert not connection.is_idle()
                assert connection.is_available()
            queued = [AsyncPoolRequest(request) for _ in range(2)]
            pool._requests.extend(queued)
            assert pool._assign_requests_to_connections() == []
            assert len(pool.connections) == 1
            assert all(waiter.connection is pool.connections[0] for waiter in queued)


class TestHTTPMultiClient:
    @pytest.mark.asyncio
    async def test_server_transport_uses_fixed_pool(self, tmp_path: Path):
        socket = tmp_path / "server.sock"
        socket.touch()
        client = HTTPMultiClient(tmp_path)
        cached = next(client._iter_clients_rand())
        transport = cached.client._transport
        assert isinstance(transport, _ServerTransport)
        pool = transport._pool
        assert isinstance(pool, _ServerConnectionPool)
        assert pool._uds == str(socket)
        assert (pool._max_connections, pool._max_keepalive_connections) == (100, 20)
        assert pool._keepalive_expiry == 5.0
        pool._network_backend = httpcore.AsyncMockBackend([RESPONSE])
        try:
            response = await client.post("/api/projects/test/get")
            assert response.status_code == 200
            assert response.text == "ok"
        finally:
            await cached.client.aclose()
            await client.aclose()
