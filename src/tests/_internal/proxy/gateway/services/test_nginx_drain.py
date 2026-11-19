import asyncio
import os
import signal
import socket
import subprocess
import tempfile
from pathlib import Path

import httpx
import psutil
import pytest

from dstack._internal.proxy.gateway.services import nginx as nginx_service
from dstack._internal.proxy.gateway.services.nginx import (
    LocationConfig,
    Nginx,
    ReplicaConfig,
    ServiceConfig,
)


@pytest.mark.asyncio
async def test_missing_worker_proof_survives_reload_failure_and_gateway_restart(
    tmp_path, system_mocks, monkeypatch
):
    monkeypatch.setattr(nginx_service, "NGINX_DRAIN_SOCKET", tmp_path / "missing.sock")
    monkeypatch.setattr(nginx_service, "NGINX_PID_FILE", tmp_path / "nginx.pid")
    (tmp_path / "sites-enabled").mkdir()
    controller = Nginx(tmp_path)
    controller.write_global_conf()
    public_config = (tmp_path / "nginx.conf").read_bytes()
    system_mocks.reload_nginx.side_effect = nginx_service.UnexpectedProxyError("reload failed")
    with pytest.raises(nginx_service.UnexpectedProxyError, match="reload failed"):
        await controller.drain()
    # Restarting Nginx itself must already load the fence, even before the Gateway retries.
    draining_config = (tmp_path / "nginx.conf").read_bytes()
    assert draining_config != public_config

    system_mocks.reload_nginx.side_effect = None
    restarted = Nginx(tmp_path)
    restarted.write_global_conf()
    assert (tmp_path / "nginx.conf").read_bytes() == draining_config
    assert not await restarted.drain()


@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.environ.get("DS002_NGINX"), reason="set DS002_NGINX to a local nginx binary"
)
@pytest.mark.parametrize("websocket", [False, True], ids=["stream", "websocket"])
async def test_ordinary_response_finishes_before_nginx_is_drained(
    tmp_path, monkeypatch, record_property, websocket
):
    # A real master and two generations of workers are required to observe a connection
    # that already bypassed the Python gateway. Launch only a disposable, unprivileged instance.
    executable = os.environ["DS002_NGINX"]
    release = asyncio.Event()
    proc = None
    with tempfile.TemporaryDirectory(dir="/tmp") as sock_dir:
        sockets = Path(sock_dir)
        probe_socket = sockets / "drain.sock"
        backend_socket = sockets / "backend.sock"
        pid = tmp_path / "nginx.pid"
        sites = tmp_path / "sites-enabled"
        sites.mkdir()
        monkeypatch.setattr(nginx_service, "sudo", lambda: [])
        read_resource = nginx_service.read_package_resource

        def resource(name):
            template = read_resource(name)
            return (
                template.replace("user www-data;", "")
                .replace("pid /run/nginx.pid;", f"pid {pid};")
                .replace("/etc/nginx/mime.types", f"{tmp_path}/mime.types")
                .replace("/etc/nginx/", f"{tmp_path}/")
                .replace("/var/log/nginx/", f"{tmp_path}/")
                .replace("/tmp/dstack-dummy-nginx.sock", str(sockets / "dummy.sock"))
                .replace(
                    "http {",
                    f"http {{\nclient_body_temp_path {tmp_path}/body;\n"
                    f"proxy_temp_path {tmp_path}/proxy;",
                )
            )

        monkeypatch.setattr(nginx_service, "read_package_resource", resource)
        monkeypatch.setattr(
            Nginx, "reload", staticmethod(lambda: proc and proc.send_signal(signal.SIGHUP))
        )
        (tmp_path / "mime.types").touch()
        controller = Nginx(tmp_path)
        # Override only OS paths that belong to the separately launched master.
        monkeypatch.setattr(nginx_service, "NGINX_PID_FILE", pid)
        monkeypatch.setattr(nginx_service, "NGINX_DRAIN_SOCKET", probe_socket)
        with socket.socket(socket.AF_INET6) as reservation:
            reservation.bind(("::1", 0))
            port = reservation.getsockname()[1]
        # IPv6 loopback exercises the public ACL, while the model proxy uses exactly 127.0.0.1.
        site = ServiceConfig(
            domain="service.test",
            project_name="p",
            https=False,
            auth=False,
            client_max_body_size=1024,
            access_log_path=tmp_path / "access.log",
            limit_req_zones=[],
            locations=[LocationConfig(prefix="/")],
            replicas=[ReplicaConfig(id="test", socket=backend_socket, port=8000)],
            proxy_buffering=False,
            read_timeout=10,
        )
        (sites / "443-service.test.conf").write_text(
            site.render().replace("listen 80;", f"listen [::1]:{port};\nlisten 127.0.0.1:{port};")
        )

        async def upstream(reader, writer):
            request = await reader.readuntil(b"\r\n\r\n")
            upgraded = websocket and request.startswith(b"GET /held ")
            if upgraded:
                # RFC 6455 example nonce, followed by complete unmasked server text frames.
                writer.write(
                    b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\n"
                    b"Connection: Upgrade\r\nSec-WebSocket-Accept: s3pPLMBiTxaQ9kYGzzhZRbK+xOo=\r\n\r\n\x81\x01A"
                )
            else:
                writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nA")
            await writer.drain()
            if request.startswith(b"GET /held "):
                await release.wait()
            writer.write(b"\x81\x01B\x88\x02\x03\xe8" if upgraded else b"B")
            await writer.drain()
            writer.close()
            await writer.wait_closed()

        backend = await asyncio.start_unix_server(upstream, path=str(backend_socket))
        controller.write_global_conf()
        command = [
            executable,
            "-p",
            str(tmp_path),
            "-c",
            str(tmp_path / "nginx.conf"),
            "-e",
            str(tmp_path / "error.log"),
            "-g",
            "daemon off;",
        ]
        try:
            proc = subprocess.Popen(command)
            async with (
                backend,
                httpx.AsyncClient(base_url=f"http://[::1]:{port}", trust_env=False) as client,
                httpx.AsyncClient(
                    base_url=f"http://127.0.0.1:{port}", trust_env=False
                ) as internal,
                asyncio.timeout(15),
            ):
                while True:
                    assert proc.poll() is None, (tmp_path / "error.log").read_text()
                    try:
                        held, connection = await asyncio.open_connection("::1", port)
                        break
                    except ConnectionRefusedError:
                        await asyncio.sleep(0.02)
                try:
                    upgrade = (
                        b"Connection: Upgrade\r\nUpgrade: websocket\r\n"
                        b"Sec-WebSocket-Version: 13\r\nSec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n"
                    )
                    connection.write(
                        b"GET /held HTTP/1.1\r\nHost: service.test\r\n"
                        + (upgrade if websocket else b"Connection: close\r\n")
                        + b"\r\n"
                    )
                    headers = await held.readuntil(b"\r\n\r\n")
                    assert headers.startswith(b"HTTP/1.1 101" if websocket else b"HTTP/1.1 200")
                    frame = b"\x81\x01" if websocket else b""
                    assert await held.readexactly(len(frame) + 1) == frame + b"A"
                    assert not await controller.drain()
                    while (await client.get("/new")).status_code == 200:
                        await asyncio.sleep(0.02)
                    status = (await client.get("/new")).status_code
                    assert status == 403
                    assert (await internal.get("/accepted-model-hop")).content == b"AB"
                    restarted = Nginx(tmp_path)
                    restarted.write_global_conf()
                    assert not await restarted.drain()
                    children = psutil.Process(proc.pid).children
                    record_property("master_pid", proc.pid)
                    record_property("workers_while_held", [p.pid for p in children()])
                    record_property("fresh_external_status", status)
                    release.set()
                    assert await held.readexactly(len(frame) + 1) == frame + b"B"
                    if websocket:
                        assert (
                            await held.readexactly(4) == b"\x88\x02\x03\xe8"
                        )  # Normal close, 1000.
                finally:
                    connection.close()
                    await connection.wait_closed()
                while not await restarted.drain():
                    await asyncio.sleep(0.02)
                record_property("workers_at_completion", [p.pid for p in children()])
                assert (await client.get("/new")).status_code == 403
        finally:
            release.set()
            backend.close()
            await backend.wait_closed()
            if proc is not None and proc.poll() is None:
                proc.terminate()
                await asyncio.to_thread(proc.wait, 5)
