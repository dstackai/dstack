import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from dstack._internal.proxy.lib.services.service_connection import (
    ServiceConnection,
    ServiceConnectionPool,
    maintain_service_connections,
)
from dstack._internal.proxy.lib.testing.common import make_project, make_service


def make_connection(alive: bool = True) -> ServiceConnection:
    service = make_service("test-proj", "test-run")
    connection = ServiceConnection(make_project("test-proj"), service, service.replicas[0])
    connection._tunnel.aopen = AsyncMock()
    connection._tunnel.aclose = AsyncMock()
    connection._tunnel.acheck = AsyncMock(return_value=alive)
    return connection


@pytest.mark.asyncio
async def test_reopen_if_exited_keeps_live_tunnel() -> None:
    connection = make_connection(alive=True)
    await connection.open()
    connection._tunnel.aopen.reset_mock()

    assert not await connection.reopen_if_exited()
    connection._tunnel.aopen.assert_not_awaited()


@pytest.mark.asyncio
async def test_reopen_if_exited_reopens_dead_tunnel_and_removes_stale_control_socket() -> None:
    connection = make_connection(alive=False)
    await connection.open()
    connection._tunnel.aopen.reset_mock()
    control_sock = Path(connection._tunnel.control_sock_path)
    control_sock.touch()

    assert await connection.reopen_if_exited()
    connection._tunnel.aopen.assert_awaited_once()
    assert not control_sock.exists()
    assert (await connection.client()) is connection._client


@pytest.mark.asyncio
async def test_reopen_if_exited_skips_unopened_and_closed_connections() -> None:
    unopened = make_connection(alive=False)
    assert not await unopened.reopen_if_exited()
    unopened._tunnel.acheck.assert_not_awaited()

    closed = make_connection(alive=False)
    await closed.open()
    await closed.close()
    closed._tunnel.aopen.reset_mock()
    assert not await closed.reopen_if_exited()
    closed._tunnel.aopen.assert_not_awaited()


@pytest.mark.asyncio
async def test_reopen_if_exited_does_not_reopen_tunnel_closed_meanwhile() -> None:
    connection = make_connection(alive=False)
    await connection.open()
    connection._tunnel.aopen.reset_mock()

    async def close_during_check() -> bool:
        connection._closed = True
        return False

    connection._tunnel.acheck = AsyncMock(side_effect=close_during_check)
    assert not await connection.reopen_if_exited()
    connection._tunnel.aopen.assert_not_awaited()


@pytest.mark.asyncio
async def test_pool_reopen_exited_continues_after_failure() -> None:
    pool = ServiceConnectionPool()
    failing = make_connection(alive=False)
    dead = make_connection(alive=False)
    live = make_connection(alive=True)
    for connection in (failing, dead, live):
        await connection.open()
        connection._tunnel.aopen.reset_mock()
    failing._tunnel.aopen.side_effect = RuntimeError("ssh failed")
    pool.connections = {"failing": failing, "dead": dead, "live": live}

    await pool.reopen_exited()

    failing._tunnel.aopen.assert_awaited_once()
    dead._tunnel.aopen.assert_awaited_once()
    live._tunnel.aopen.assert_not_awaited()


@pytest.mark.asyncio
async def test_maintain_service_connections_checks_periodically() -> None:
    pool = ServiceConnectionPool()
    pool.reopen_exited = AsyncMock(side_effect=[RuntimeError("check failed"), None, None])
    task = asyncio.create_task(maintain_service_connections(pool, interval=0.01))
    for _ in range(100):
        if pool.reopen_exited.await_count >= 3:
            break
        await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert pool.reopen_exited.await_count >= 3
