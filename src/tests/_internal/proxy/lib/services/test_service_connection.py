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
        tunnel.exits.put_nowait(255)
        await _yield_to_event_loop()

        # Recovery runs without an HTTP request and keeps Nginx's configured socket.
        tunnel_factory.assert_called_once()
        assert tunnel.aopen.await_count == 2
        tunnel.aclose.assert_awaited_once()
        tunnel.acheck.assert_not_awaited()
        assert not monitor_clock.tasks
        assert tunnel_factory.call_args.kwargs["background"] is False
        assert connection.app_socket_path == socket_path
        assert tunnel_factory.call_args.kwargs["forwarded_sockets"][0].local.path == socket_path

    async def test_healthy_gateway_does_not_reopen_or_start_duplicate_monitors(
        self, project, service, pool, tunnel_factory, monitor_clock
    ):
        connection = await pool.get_or_add(project, service, service.replicas[0])
        await connection.open()

        await _yield_to_event_loop()

        tunnel_factory.return_value.aopen.assert_awaited_once()
        tunnel_factory.return_value.wait_closed.assert_awaited_once()
        tunnel_factory.return_value.acheck.assert_not_awaited()
        assert not monitor_clock.tasks

    async def test_failed_reconnects_back_off_and_then_recover(
        self, project, service, pool, tunnel_factory, monitor_clock
    ):
        tunnel = tunnel_factory.return_value
        connection = await pool.get_or_add(project, service, service.replicas[0])
        original_client = await connection.client()
        tunnel.aopen.side_effect = [SSHError("offline"), SSHError("offline"), None]
        tunnel.exits.put_nowait(255)
        await _yield_to_event_loop()

        assert 0.5 <= await monitor_clock.tick() <= 1
        assert 1 <= await monitor_clock.tick() <= 2

        assert tunnel.aopen.await_count == 4
        assert await asyncio.wait_for(connection.client(), timeout=1) is original_client
        assert not original_client.is_closed

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
        assert not monitor_clock.tasks

    async def test_in_server_connection_does_not_monitor(
        self, project, service, pool, tunnel_factory, monitor_clock
    ):
        service = service.model_copy(update={"domain": None})
        connection = await pool.get_or_add(project, service, service.replicas[0])
        await _yield_to_event_loop()

        assert not (await connection.client()).is_closed
        tunnel_factory.return_value.aopen.assert_awaited_once()
        tunnel_factory.return_value.wait_closed.assert_not_awaited()
        assert tunnel_factory.call_args.kwargs["background"] is True
        assert not monitor_clock.tasks

    async def test_client_does_not_wait_for_a_blocked_reconnect(
        self, project, service, pool, tunnel_factory, monitor_clock
    ):
        tunnel = tunnel_factory.return_value
        connection = await pool.get_or_add(project, service, service.replicas[0])
        original_client = await connection.client()
        reconnecting = asyncio.Event()
        release_reconnect = asyncio.Event()

        async def reconnect():
            reconnecting.set()
            await release_reconnect.wait()

        tunnel.aopen.side_effect = reconnect
        tunnel.exits.put_nowait(255)
        await _yield_to_event_loop()
        assert reconnecting.is_set()

        # The timeout is only a deadlock guard; the reconnect stays blocked throughout.
        client = await asyncio.wait_for(connection.client(), timeout=1)
        assert client is original_client
        assert not release_reconnect.is_set()

    @pytest.mark.parametrize("remove_from_pool", [False, True], ids=["close", "remove"])
    async def test_close_cancels_reconnect_before_final_tunnel_cleanup(
        self, project, service, pool, tunnel_factory, monitor_clock, remove_from_pool
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
        monitor_task = connection._monitor_task
        tunnel.exits.put_nowait(255)
        await _yield_to_event_loop()
        assert lifecycle == ["closed", "reconnecting"]

        if remove_from_pool:
            await pool.remove(service.replicas[0].id)
            assert await pool.get(service.replicas[0].id) is None
        else:
            await connection.close()

        release_reconnect.set()
        await _yield_to_event_loop()
        assert lifecycle == ["closed", "reconnecting", "cancelled", "closed"]
        assert client.is_closed
        assert monitor_task.cancelled()
        with pytest.raises(UnexpectedProxyError, match="closed"):
            await connection.open()
        assert tunnel.aopen.await_count == 2


@pytest.mark.asyncio
class TestServiceConnectionPool:
    @pytest.mark.parametrize("cancel_count", [1, 2])
    async def test_cancelled_removal_finishes_monitor_and_resource_cleanup(
        self, project, service, pool, tunnel_factory, cancel_count
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
            for _ in range(cancel_count):
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

    async def test_initial_open_failure_closes_tunnel_and_removes_connection(
        self, project, service, pool, tunnel_factory, monitor_clock
    ):
        tunnel = tunnel_factory.return_value
        tunnel.aopen.side_effect = RuntimeError("cannot reach replica")

        with pytest.raises(RuntimeError, match="cannot reach replica"):
            await pool.get_or_add(project, service, service.replicas[0])

        assert await pool.get(service.replicas[0].id) is None
        tunnel.aclose.assert_awaited_once()
        assert not monitor_clock.tasks

    async def test_cancelled_initial_open_closes_tunnel_and_removes_connection(
        self, project, service, pool, tunnel_factory, monitor_clock
    ):
        tunnel = tunnel_factory.return_value
        opening = asyncio.Event()

        async def open_tunnel():
            opening.set()
            await asyncio.Event().wait()

        tunnel.aopen.side_effect = open_tunnel
        adding = asyncio.create_task(pool.get_or_add(project, service, service.replicas[0]))
        try:
            await _yield_to_event_loop()
            assert opening.is_set()
            adding.cancel()
            with pytest.raises(asyncio.CancelledError):
                await adding
        finally:
            adding.cancel()
            await asyncio.gather(adding, return_exceptions=True)

        assert await pool.get(service.replicas[0].id) is None
        tunnel.aclose.assert_awaited_once()
        assert not monitor_clock.tasks

    async def test_remove_finishing_after_readd_keeps_new_connection(
        self, project, service, pool, tunnel_factory, monitor_clock
    ):
        old_tunnel = tunnel_factory.return_value
        new_tunnel = _make_tunnel()
        tunnel_factory.side_effect = [old_tunnel, new_tunnel]
        replica = service.replicas[0]
        await pool.get_or_add(project, service, replica)
        closing = asyncio.Event()
        release_close = asyncio.Event()

        async def close_tunnel():
            closing.set()
            await release_close.wait()

        old_tunnel.aclose.side_effect = close_tunnel
        removing = asyncio.create_task(pool.remove(replica.id))
        try:
            await asyncio.wait_for(closing.wait(), timeout=1)
            assert await pool.get(replica.id) is None
            replacement = await pool.get_or_add(project, service, replica)
        finally:
            release_close.set()
            await removing

        assert closing.is_set()
        assert await pool.get(replica.id) is replacement
        assert not (await replacement.client()).is_closed
        new_tunnel.aclose.assert_not_awaited()

    async def test_failed_open_cleanup_after_readd_keeps_new_connection(
        self, project, service, pool, tunnel_factory, monitor_clock
    ):
        old_tunnel = tunnel_factory.return_value
        new_tunnel = _make_tunnel()
        tunnel_factory.side_effect = [old_tunnel, new_tunnel]
        replica = service.replicas[0]
        release_open = asyncio.Event()

        async def open_tunnel():
            await release_open.wait()
            raise RuntimeError("old connection failed")

        old_tunnel.aopen.side_effect = open_tunnel
        adding = asyncio.create_task(pool.get_or_add(project, service, replica))
        removing = None
        try:
            await _yield_to_event_loop()
            removing = asyncio.create_task(pool.remove(replica.id))
            await _yield_to_event_loop()
            replacement = await pool.get_or_add(project, service, replica)
            release_open.set()
            with pytest.raises(RuntimeError, match="old connection failed"):
                await adding
            await removing

            assert await pool.get(replica.id) is replacement
            assert not (await replacement.client()).is_closed
            old_tunnel.aclose.assert_awaited()
            new_tunnel.aclose.assert_not_awaited()
        finally:
            release_open.set()
            adding.cancel()
            await asyncio.gather(adding, return_exceptions=True)
            if removing is not None:
                await removing

    async def test_removed_initial_open_succeeding_cannot_resurrect_or_remove_replacement(
        self, project, service, pool, tunnel_factory, monitor_clock
    ):
        old_tunnel = tunnel_factory.return_value
        new_tunnel = _make_tunnel()
        tunnel_factory.side_effect = [old_tunnel, new_tunnel]
        replica = service.replicas[0]
        release_open = asyncio.Event()

        async def open_tunnel():
            await release_open.wait()

        old_tunnel.aopen.side_effect = open_tunnel
        adding = asyncio.create_task(pool.get_or_add(project, service, replica))
        removing = None
        try:
            await _yield_to_event_loop()
            original = await pool.get(replica.id)
            assert original is not None
            removing = asyncio.create_task(pool.remove(replica.id))
            await _yield_to_event_loop()
            replacement = await pool.get_or_add(project, service, replica)
            await _yield_to_event_loop()
            replacement_monitor = replacement._monitor_task
            assert replacement_monitor is not None

            release_open.set()
            with pytest.raises(UnexpectedProxyError, match="removed while opening"):
                await adding
            await removing

            assert await pool.get(replica.id) is replacement
            assert not (await replacement.client()).is_closed
            assert replacement._monitor_task is replacement_monitor
            assert not replacement_monitor.done()
            old_tunnel.aopen.assert_awaited_once()
            old_tunnel.wait_closed.assert_not_awaited()
            old_tunnel.aclose.assert_awaited()
            new_tunnel.aclose.assert_not_awaited()
            with pytest.raises(UnexpectedProxyError, match="closed"):
                await original.open()
        finally:
            release_open.set()
            adding.cancel()
            await asyncio.gather(adding, return_exceptions=True)
            if removing is not None:
                await removing

    async def test_remove_all_cancels_every_monitor_even_if_one_close_fails(
        self, project, service, pool, tunnel_factory, monitor_clock
    ):
        tunnels = [_make_tunnel() for _ in range(2)]
        tunnel_factory.side_effect = tunnels
        clients = []
        monitors = []
        for index in range(2):
            replica = service.replicas[0].model_copy(update={"id": f"replica-{index}"})
            connection = await pool.get_or_add(project, service, replica)
            clients.append(await connection.client())
            monitors.append(connection._monitor_task)
        await _yield_to_event_loop()
        tunnels[0].aclose.side_effect = RuntimeError("already gone")

        await pool.remove_all()

        assert not pool.connections
        assert all(task.cancelled() for task in monitors)
        assert all(client.is_closed for client in clients)
        for tunnel in tunnels:
            tunnel.aclose.assert_awaited_once()

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
        self.tasks = set()

    async def sleep(self, delay):
        self.tasks.add(asyncio.current_task())
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
