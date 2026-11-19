import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from dstack._internal.core.errors import SSHError
from dstack._internal.server.services.gateways.connection import GatewayConnection
from dstack._internal.server.services.gateways.pool import GatewayConnectionsPool


@pytest.mark.asyncio
async def test_recycled_address_does_not_reuse_previous_replicas_tunnel():
    pool = GatewayConnectionsPool()
    with patch("dstack._internal.server.services.gateways.pool.GatewayConnection") as factory:
        old = AsyncMock()
        replacement = AsyncMock()
        factory.side_effect = [old, replacement]
        assert await pool.get_or_add("host", "first key") is old
        assert await pool.get_or_add("host", "second key") is replacement
        old.close.assert_awaited_once()
        assert await pool.get_or_add("host", "second key") is replacement
        assert await pool.all() == [replacement]


@pytest.mark.asyncio
async def test_opening_one_host_does_not_expose_unready_connection_or_block_other_hosts():
    pool = GatewayConnectionsPool()
    entered, release = asyncio.Event(), asyncio.Event()

    async def delayed_open(**kwargs):
        entered.set()
        await release.wait()

    slow, other = AsyncMock(), AsyncMock()
    slow.open.side_effect = delayed_open
    with patch(
        "dstack._internal.server.services.gateways.pool.GatewayConnection",
        side_effect=[slow, other],
    ):
        first = asyncio.create_task(pool.get_or_add("slow", "key"))
        await entered.wait()
        second = asyncio.create_task(pool.get_or_add("slow", "key"))
        try:
            async with asyncio.timeout(2):
                assert await pool.get_or_add("other", "key") is other
            assert await pool.all() == [other]
        finally:
            release.set()
            assert await first is slow
            assert await second is slow
        slow.open.assert_awaited_once()


@pytest.mark.asyncio
async def test_socket_paths_are_scoped_to_key_and_invalidated_after_close(tmp_path):
    # Two server processes can have independent pools that use the same server directory.
    with (
        patch("dstack._internal.server.settings.SERVER_DIR_PATH", tmp_path),
        patch("dstack._internal.server.services.gateways.connection.SSHTunnel", autospec=True),
    ):
        first = GatewayConnection("host", "first key", 8000)
        second = GatewayConnection("host", "second key", 8000)
        restarted = GatewayConnection("host", "second key", 8000)
        assert first.gateway_socket_path.resolve() != second.gateway_socket_path.resolve()
        assert second.gateway_socket_path.resolve() == restarted.gateway_socket_path.resolve()
        await first.close()
        assert not await first.check_or_restart()
        with pytest.raises(SSHError):
            async with first.client():
                pytest.fail("Retired connection returned a usable client")
        assert not first.gateway_socket_path.parent.exists()
        assert not first.gateway_socket_path.parent.is_symlink()


@pytest.mark.asyncio
async def test_startup_closes_pre_upgrade_control_socket_without_using_it_for_forwarding(tmp_path):
    address_dir = tmp_path / "gateway-connections" / "host"
    address_dir.mkdir(parents=True)
    old_control = address_dir / "control.sock"
    old_control.touch()
    tunnels = {}

    def tunnel(**kwargs):
        control = Path(kwargs["control_sock_path"]).resolve()
        mock = AsyncMock(destination=kwargs["destination"], identity_path="identity")
        mock.acheck.return_value = False
        tunnels[control] = mock
        return mock

    with (
        patch("dstack._internal.server.settings.SERVER_DIR_PATH", tmp_path),
        patch(
            "dstack._internal.server.services.gateways.connection.SSHTunnel", side_effect=tunnel
        ),
    ):
        conn = GatewayConnection("host", "new key", 8000)
        await conn.open(close_existing_tunnel=True)
        tunnels[old_control].aclose.assert_awaited_once()
        tunnels[old_control].aopen.assert_not_awaited()
        assert conn.tunnel is tunnels[conn.connection_dir / "control.sock"]
        assert conn.gateway_socket_path.resolve().parent != address_dir
        await conn.close()
