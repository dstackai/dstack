import asyncio
from typing import AsyncIterator
from unittest.mock import create_autospec

import pytest
import pytest_asyncio

from dstack._internal.core.errors import SSHError
from dstack._internal.core.services.ssh.tunnel import SSHTunnel
from dstack._internal.proxy.lib.errors import UnexpectedProxyError
from dstack._internal.proxy.lib.services import service_connection
from dstack._internal.proxy.lib.services.service_connection import ServiceConnectionPool
from dstack._internal.proxy.lib.testing.common import make_project, make_service


@pytest.fixture
def project():
    return make_project("test-project")


@pytest.fixture
def service():
    return make_service("test-project", "test-service", domain="service.gateway.test")


@pytest.fixture
def tunnel_factory(mocker):
    factory = mocker.patch.object(service_connection, "SSHTunnel", autospec=True)
    factory.return_value = _make_tunnel()
    return factory


@pytest.fixture
def monitor_clock(monkeypatch):
    clock = _MonitorClock()
    monkeypatch.setattr(service_connection.asyncio, "sleep", clock.sleep)
    return clock


@pytest_asyncio.fixture
async def pool() -> AsyncIterator[ServiceConnectionPool]:
    pool = ServiceConnectionPool()
    try:
        yield pool
    finally:
        await pool.remove_all()


@pytest.mark.asyncio
class TestServiceConnection:
    async def test_gateway_recovers_the_same_tunnel_and_socket_without_polling(
        self, project, service, pool, tunnel_factory, monitor_clock
    ):
        tunnel = tunnel_factory.return_value
        connection = await pool.get_or_add(project, service, service.replicas[0])
        socket_path = connection.app_socket_path
        await connection.open()
        await _yield_to_event_loop()
        tunnel.aopen.assert_awaited_once()
        tunnel.wait_closed.assert_awaited_once()

        tunnel.exits.put_nowait(255)
        await _yield_to_event_loop()

        # Recovery runs without an HTTP request and keeps Nginx's configured socket.
        tunnel_factory.assert_called_once()
        assert tunnel.aopen.await_count == 2
        tunnel.aclose.assert_awaited_once()
        tunnel.acheck.assert_not_awaited()
        assert monitor_clock.pending.empty()
        assert tunnel_factory.call_args.kwargs["background"] is False
        assert connection.app_socket_path == socket_path
        assert tunnel_factory.call_args.kwargs["forwarded_sockets"][0].local.path == socket_path

    async def test_failed_reconnects_back_off_and_then_recover(
        self, project, service, pool, tunnel_factory, monitor_clock
    ):
        tunnel = tunnel_factory.return_value
        await pool.get_or_add(project, service, service.replicas[0])
        tunnel.aopen.side_effect = [SSHError("offline"), SSHError("offline"), None]
        tunnel.exits.put_nowait(255)
        await _yield_to_event_loop()

        assert 0.5 <= await monitor_clock.tick() <= 1
        assert 1 <= await monitor_clock.tick() <= 2

        assert tunnel.aopen.await_count == 4

    async def test_repeated_early_exits_back_off_to_a_bounded_delay(
        self, project, service, pool, tunnel_factory, monitor_clock
    ):
        tunnel = tunnel_factory.return_value
        await pool.get_or_add(project, service, service.replicas[0])
        tunnel.exits.put_nowait(255)
        await _yield_to_event_loop()
        for maximum in (1, 2, 4, 8, 16, 30, 30):
            tunnel.exits.put_nowait(255)
            await _yield_to_event_loop()
            assert maximum / 2 <= await monitor_clock.tick() <= maximum

    async def test_stable_tunnel_resets_retry_delay(
        self, project, service, pool, tunnel_factory, monitor_clock, mocker
    ):
        clock = mocker.patch.object(asyncio.get_running_loop(), "time", return_value=0)
        tunnel = tunnel_factory.return_value
        await pool.get_or_add(project, service, service.replicas[0])
        tunnel.exits.put_nowait(255)
        await _yield_to_event_loop()
        clock.return_value = service_connection.MAX_TUNNEL_RECONNECT_DELAY
        tunnel.exits.put_nowait(255)
        await _yield_to_event_loop()

        assert tunnel.aopen.await_count == 3
        assert monitor_clock.pending.empty()

    async def test_in_server_connection_does_not_monitor(
        self, project, service, pool, tunnel_factory
    ):
        service = service.model_copy(update={"domain": None})
        connection = await pool.get_or_add(project, service, service.replicas[0])
        await _yield_to_event_loop()

        assert not (await connection.client()).is_closed
        tunnel_factory.return_value.aopen.assert_awaited_once()
        tunnel_factory.return_value.wait_closed.assert_not_awaited()
        assert tunnel_factory.call_args.kwargs["background"] is True

    async def test_removal_cancels_reconnect_before_final_tunnel_cleanup(
        self, project, service, pool, tunnel_factory
    ):
        tunnel = tunnel_factory.return_value
        connection = await pool.get_or_add(project, service, service.replicas[0])
        client = await connection.client()
        release_reconnect = asyncio.Event()
        lifecycle = []

        async def reconnect():
            lifecycle.append("reconnecting")
            try:
                await release_reconnect.wait()
            except asyncio.CancelledError:
                lifecycle.append("cancelled")
                raise

        async def close_tunnel():
            lifecycle.append("closed")

        tunnel.aopen.side_effect = reconnect
        tunnel.aclose.side_effect = close_tunnel
        tunnel.exits.put_nowait(255)
        await _yield_to_event_loop()
        assert lifecycle == ["closed", "reconnecting"]

        await pool.remove(service.replicas[0].id)

        release_reconnect.set()
        await _yield_to_event_loop()
        assert await pool.get(service.replicas[0].id) is None
        assert lifecycle == ["closed", "reconnecting", "cancelled", "closed"]
        assert client.is_closed
        with pytest.raises(UnexpectedProxyError, match="closed"):
            await connection.open()
        assert tunnel.aopen.await_count == 2


@pytest.mark.asyncio
class TestServiceConnectionPool:
    async def test_cancelled_removal_finishes_monitor_and_resource_cleanup(
        self, project, service, pool, tunnel_factory
    ):
        tunnel = tunnel_factory.return_value
        waiting = asyncio.Event()
        monitor_cancelled = asyncio.Event()
        release_monitor = asyncio.Event()

        async def wait_closed():
            waiting.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                monitor_cancelled.set()
                await release_monitor.wait()
                raise

        tunnel.wait_closed.side_effect = wait_closed
        replica = service.replicas[0]
        connection = await pool.get_or_add(project, service, replica)
        client = await connection.client()
        await waiting.wait()
        removing = asyncio.create_task(pool.remove(replica.id))
        try:
            await monitor_cancelled.wait()
            for _ in range(2):
                removing.cancel()
                await _yield_to_event_loop()
                assert not removing.done()
        finally:
            release_monitor.set()
            with pytest.raises(asyncio.CancelledError):
                await removing

        assert await pool.get(replica.id) is None
        assert client.is_closed
        assert connection._monitor_task is None
        tunnel.aclose.assert_awaited_once()

    @pytest.mark.parametrize("error", [RuntimeError, asyncio.CancelledError])
    async def test_initial_open_failure_closes_tunnel_and_removes_connection(
        self, project, service, pool, tunnel_factory, error
    ):
        tunnel = tunnel_factory.return_value
        tunnel.aopen.side_effect = error("cannot reach replica")

        with pytest.raises(error):
            await pool.get_or_add(project, service, service.replicas[0])

        assert await pool.get(service.replicas[0].id) is None
        tunnel.aclose.assert_awaited_once()
        tunnel.wait_closed.assert_not_awaited()

    async def test_removed_initial_open_succeeding_cannot_resurrect_or_remove_replacement(
        self, project, service, pool, tunnel_factory
    ):
        old_tunnel = tunnel_factory.return_value
        new_tunnel = _make_tunnel()
        tunnel_factory.side_effect = [old_tunnel, new_tunnel]
        replica = service.replicas[0]
        opening = asyncio.Event()
        release_open = asyncio.Event()

        async def open_tunnel():
            opening.set()
            await release_open.wait()

        old_tunnel.aopen.side_effect = open_tunnel
        adding = asyncio.create_task(pool.get_or_add(project, service, replica))
        removing = None
        try:
            await opening.wait()
            removing = asyncio.create_task(pool.remove(replica.id))
            await _yield_to_event_loop()
            replacement = await pool.get_or_add(project, service, replica)

            release_open.set()
            with pytest.raises(UnexpectedProxyError, match="removed while opening"):
                await adding
            await removing

            assert await pool.get(replica.id) is replacement
            assert not (await replacement.client()).is_closed
            old_tunnel.wait_closed.assert_not_awaited()
            old_tunnel.aclose.assert_awaited()
            new_tunnel.wait_closed.assert_awaited_once()
            new_tunnel.aclose.assert_not_awaited()
        finally:
            release_open.set()
            adding.cancel()
            await asyncio.gather(adding, return_exceptions=True)
            if removing is not None:
                await removing

    async def test_reconnect_limit_is_shared_and_removal_cancels_queued_reconnects(
        self, project, service, pool, tunnel_factory
    ):
        count = service_connection.MAX_CONCURRENT_TUNNEL_RECONNECTS + 3
        tunnels = [_make_tunnel() for _ in range(count)]
        tunnel_factory.side_effect = tunnels
        active = 0
        peak = 0
        started = asyncio.Event()
        release = asyncio.Event()

        async def reconnect():
            nonlocal active, peak
            active += 1
            peak = max(active, peak)
            if active == service_connection.MAX_CONCURRENT_TUNNEL_RECONNECTS:
                started.set()
            try:
                await release.wait()
            finally:
                active -= 1

        for index, tunnel in enumerate(tunnels):
            replica = service.replicas[0].model_copy(update={"id": f"replica-{index}"})
            await pool.get_or_add(project, service, replica)
            tunnel.aopen.side_effect = reconnect
            tunnel.exits.put_nowait(255)
        await asyncio.wait_for(started.wait(), timeout=1)
        await _yield_to_event_loop()

        # All tunnels have exited, but only a bounded number are starting SSH processes.
        assert peak == service_connection.MAX_CONCURRENT_TUNNEL_RECONNECTS
        await pool.remove_all()
        release.set()
        await _yield_to_event_loop()
        assert active == 0
        assert not pool.connections
        assert sum(t.aopen.await_count - 1 for t in tunnels) == peak


class _MonitorClock:
    """Wake monitor timers explicitly, without waiting for wall-clock time."""

    def __init__(self):
        self.pending = asyncio.Queue()

    async def sleep(self, delay):
        wakeup = asyncio.get_running_loop().create_future()
        self.pending.put_nowait((delay, wakeup))
        await wakeup

    async def tick(self):
        await _yield_to_event_loop()
        delay, wakeup = self.pending.get_nowait()
        wakeup.set_result(None)
        await _yield_to_event_loop()
        return delay


def _make_tunnel():
    tunnel = create_autospec(SSHTunnel, instance=True)
    tunnel.exits = asyncio.Queue()
    tunnel.wait_closed.side_effect = tunnel.exits.get
    return tunnel


async def _yield_to_event_loop():
    ready = asyncio.get_running_loop().create_future()
    asyncio.get_running_loop().call_soon(ready.set_result, None)
    await ready
