import asyncio
import socket
import uuid
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from dstack._internal.core.errors import SSHError
from dstack._internal.core.models.instances import SSHConnectionParams
from dstack._internal.core.services.ssh.tunnel import IPSocket, SocketPair, UnixSocket
from dstack._internal.server.services.jobs import server_connection
from dstack._internal.server.services.jobs.server_connection import (
    JobServerConnection,
    JobServerConnectionsPool,
)
from dstack._internal.utils.path import FileContent


@pytest.fixture
def tunnel_mock(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(server_connection, "CONNECTIONS_DIR", tmp_path)
    tunnel = MagicMock()
    tunnel.acheck = AsyncMock(return_value=False)
    tunnel.aopen = AsyncMock()
    tunnel.aexec = AsyncMock(return_value="")
    tunnel.aclose = AsyncMock()
    tunnel_class = Mock(return_value=tunnel)
    monkeypatch.setattr(server_connection, "SSHTunnel", tunnel_class)
    monkeypatch.setattr(
        server_connection,
        "get_container_ssh_credentials",
        Mock(
            return_value=[
                (
                    SSHConnectionParams(hostname="job.example.com", username="root", port=10022),
                    FileContent("private-key"),
                )
            ]
        ),
    )
    return tunnel, tunnel_class


class TestJobServerConnection:
    @pytest.mark.asyncio
    async def test_opens_private_reverse_socket(self, tunnel_mock):
        tunnel, tunnel_class = tunnel_mock
        job = Mock(id=uuid.uuid4())
        connection = JobServerConnection(job, job_runtime_data=None)
        connection._server_is_reachable = AsyncMock(return_value=True)

        await connection.open()

        tunnel_class.assert_called_once()
        assert tunnel.aopen.await_count == 2
        assert tunnel.reverse_forwarded_sockets == [
            SocketPair(
                local=IPSocket(host="127.0.0.1", port=server_connection.settings.SERVER_PORT),
                remote=UnixSocket(path=server_connection._REMOTE_SOCKET_PATH),
            )
        ]
        assert tunnel.forwarded_sockets == [
            SocketPair(
                local=UnixSocket(path=connection._probe_socket_path),
                remote=UnixSocket(path=server_connection._REMOTE_SOCKET_PATH),
            )
        ]
        commands = [call.args[0] for call in tunnel.aexec.await_args_list]
        assert commands == [
            "mkdir -p /run/dstack && chmod 755 /run/dstack && rm -f /run/dstack/server.sock",
            "chmod 666 /run/dstack/server.sock",
        ]

    @pytest.mark.asyncio
    async def test_reuses_live_tunnel_with_existing_socket(self, tunnel_mock):
        tunnel, _ = tunnel_mock
        tunnel.acheck.return_value = True
        job = Mock(id=uuid.uuid4())
        connection = JobServerConnection(job, job_runtime_data=None)
        connection._server_is_reachable = AsyncMock(return_value=True)
        connection._real_control_socket_path.touch()

        await connection.open()

        tunnel.aopen.assert_not_awaited()
        connection._server_is_reachable.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_replaces_tunnel_with_stale_socket(self, tunnel_mock):
        tunnel, _ = tunnel_mock
        tunnel.acheck.return_value = True
        job = Mock(id=uuid.uuid4())
        connection = JobServerConnection(job, job_runtime_data=None)
        connection._server_is_reachable = AsyncMock(side_effect=[False, True])
        connection._real_control_socket_path.touch()

        await connection.open()

        tunnel.aclose.assert_awaited_once()
        assert tunnel.aopen.await_count == 2

    @pytest.mark.asyncio
    async def test_stale_probe_socket_is_not_reachable(self, tunnel_mock):
        job = Mock(id=uuid.uuid4())
        connection = JobServerConnection(job, job_runtime_data=None)
        stale_socket = socket.socket(socket.AF_UNIX)
        stale_socket.bind(str(connection._probe_socket_path))
        stale_socket.close()

        assert not await connection._server_is_reachable()

    @pytest.mark.asyncio
    async def test_healthcheck_through_probe_socket(self, tunnel_mock):
        job = Mock(id=uuid.uuid4())
        connection = JobServerConnection(job, job_runtime_data=None)

        async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
            await reader.readuntil(b"\r\n\r\n")
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n")
            await writer.drain()
            writer.close()

        server = await asyncio.start_unix_server(handle, path=connection._probe_socket_path)
        try:
            assert await connection._server_is_reachable()
        finally:
            server.close()
            await server.wait_closed()


class TestJobServerConnectionsPool:
    @pytest.mark.asyncio
    async def test_reuses_healthy_connection(self):
        job = Mock(id=uuid.uuid4())
        connection = MagicMock()
        connection.job_id = job.id
        connection.open = AsyncMock()
        connection.is_alive = AsyncMock(return_value=True)
        connection.close = AsyncMock()
        pool = JobServerConnectionsPool()

        with patch.object(server_connection, "JobServerConnection", return_value=connection):
            assert await pool.ensure(job, job_runtime_data=None)
            assert await pool.ensure(job, job_runtime_data=None)

        connection.open.assert_awaited_once()
        connection.is_alive.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_false_when_tunnel_cannot_open(self):
        job = Mock(id=uuid.uuid4())
        connection = MagicMock()
        connection.job_id = job.id
        connection.open = AsyncMock(side_effect=SSHError("connection failed"))
        connection.close = AsyncMock()
        pool = JobServerConnectionsPool()

        with patch.object(server_connection, "JobServerConnection", return_value=connection):
            with patch.object(server_connection.time, "monotonic", side_effect=[10, 131]):
                assert not await pool.ensure(job, job_runtime_data=None)
                assert pool.retry_timed_out(job.id, timeout=120)

        connection.close.assert_awaited_once()
