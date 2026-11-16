"""Opt-in real Nginx topology, with Unix fixture sockets replacing SSH tunnels."""

import asyncio
import json
import os
import shutil
import socket
import subprocess
import time

import httpx
import pytest

from dstack._internal.proxy.gateway.const import PROXY_PORT_ON_GATEWAY
from dstack._internal.proxy.gateway.services.nginx import (
    LimitReqConfig,
    LimitReqZoneConfig,
    LocationConfig,
    ModelEntrypointConfig,
    ReplicaConfig,
    ServiceConfig,
)
from tests._internal.proxy.gateway.metering.harness import Harness


def configs(root, backend_socket):
    model = ModelEntrypointConfig(
        domain="model.test", project_name="p", https=False, read_timeout=10
    )
    service = ServiceConfig(
        domain="service.test",
        project_name="p",
        https=False,
        auth=True,
        client_max_body_size=1024 * 1024,
        access_log_path=root / "access.log",
        limit_req_zones=[LimitReqZoneConfig(name="test_limit", key="$binary_remote_addr", rpm=1)],
        locations=[
            LocationConfig(
                prefix="/limited", limit_req=LimitReqConfig(zone="test_limit", burst=0)
            ),
            LocationConfig(prefix="/"),
        ],
        replicas=[ReplicaConfig(id="test-replica", socket=backend_socket, port=8000)],
        cors_enabled=True,
        proxy_buffering=False,
        read_timeout=10,
    )
    return model, service


def test_rendered_routes_keep_management_private(tmp_path):
    model, service = configs(tmp_path, tmp_path / "backend.sock")
    public = model.render()
    direct = service.render()
    assert "/api/models/p/" in public
    assert "proxy_pass http://service.test.upstream" in direct
    assert "/api/usage" not in public + direct
    assert "internal;" in direct and "limit_req_status 429;" in direct
    assert "proxy_buffering off;" in direct and "set $dstack_replica_hit 1;" in direct


@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.environ.get("DS002_NGINX"), reason="set DS002_NGINX to a local nginx binary"
)
async def test_real_nginx_ingress(tmp_path):
    # Real Nginx earns its process cost: buffering, URI normalization, CORS and auth subrequests.
    executable = os.environ["DS002_NGINX"]
    assert shutil.which(executable), "DS002_NGINX must point to a working binary"
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    url = f"http://127.0.0.1:{port}"
    h = Harness(tmp_path, nginx_url=url)
    proc = None
    await h.start()
    try:
        model, service = configs(tmp_path, h.backend_socket)
        proxy_port = httpx.URL(h.gateway_url).port
        rendered = "\n".join(c.render() for c in (model, service))
        rendered = rendered.replace("listen 80;", f"listen 127.0.0.1:{port};")
        rendered = rendered.replace("localhost:8000", f"127.0.0.1:{proxy_port}")
        # Production default is 8000; assert every upstream points to the isolated listener.
        rendered = rendered.replace(
            f"localhost:{PROXY_PORT_ON_GATEWAY}", f"127.0.0.1:{proxy_port}"
        )
        conf = f"""daemon off;
master_process off;
pid {tmp_path}/nginx.pid;
error_log {tmp_path}/error.log info;
events {{ worker_connections 128; }}
http {{
  access_log off;
  client_body_temp_path {tmp_path}/body;
  proxy_temp_path {tmp_path}/proxy;
  log_format dstack_stat '$time_iso8601 $host $status $request_time $dstack_replica_hit';
  {rendered}
}}
"""
        config_path = tmp_path / "nginx.conf"
        config_path.write_text(conf)
        proc = subprocess.Popen(
            [executable, "-p", str(tmp_path), "-c", str(config_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        async with httpx.AsyncClient(base_url=url, timeout=10) as client:
            deadline = time.monotonic() + 10
            while True:
                if proc.poll() is not None:
                    raise RuntimeError((tmp_path / "error.log").read_text())
                try:
                    await client.get("/", headers={"Host": "model.test"})
                    break
                except httpx.ConnectError:
                    if time.monotonic() > deadline:
                        raise
                    await asyncio.sleep(0.02)
            body = {
                "model": "model-a",
                "user": "ingress",
                "messages": [{"role": "user", "content": "A"}],
                "stream": True,
                "stream_options": {"include_usage": True},
            }
            await h.backend_control(hold=["ingress"])
            async with client.stream(
                "POST",
                "/chat/completions",
                json=body,
                headers={
                    "Host": "model.test",
                    "Authorization": "Bearer token-a",
                    "X-Test-Request-ID": "ingress",
                },
            ) as response:
                response.raise_for_status()
                seen = []
                async for line in response.aiter_lines():
                    if line.startswith("data:"):
                        if not seen:
                            assert "Hello" in line
                            await h.backend_control(release=["ingress"])
                        seen.append(line)
                assert seen[-1] == "data: [DONE]"
            await h.wait_finalized("ingress")
            await h.advance_clock()
            page = await h.batches()
            assert page["batches"][0]["entries"][0]["completion_tokens"] == 3
            # Service hostname bypasses Python; valid inference works but adds no counters.
            body.update(stream=False, user="direct")
            response = await client.post(
                "/v1/chat/completions", json=body, headers={"Host": "service.test"}
            )
            assert (
                response.status_code == 200 and response.json()["usage"]["completion_tokens"] == 3
            )
            await h.advance_clock()
            assert (await h.batches()) == page
            variants = [
                "/api/usage/batches",
                "/api/usage/batches/ack",
                "/../api/usage/batches",
                "/%2e%2e/api/usage/batches",
                "/%2e%2e%2f%2e%2e%2fusage/batches",
                "//api/usage/batches",
                "/chat/completions/../../usage/batches",
            ]
            for host in ["model.test", "service.test"]:
                for path in variants:
                    for method in ["GET", "POST"]:
                        response = await client.request(
                            method,
                            path,
                            json={"batch_ids": [page["batches"][0]["batch_id"]]},
                            headers={"Host": host, "Authorization": "Bearer token-a"},
                        )
                        assert response.status_code in (400, 403, 404, 405, 422), (
                            host,
                            path,
                            method,
                            response.text,
                        )
            assert (await h.batches()) == page
            cors = await client.options(
                "/v1/chat/completions",
                headers={"Host": "service.test", "Origin": "https://example.test"},
            )
            assert cors.status_code == 204 and cors.headers["access-control-allow-origin"] == "*"
            statuses = [
                (await client.get("/limited", headers={"Host": "service.test"})).status_code
                for _ in range(3)
            ]
            assert 429 in statuses
        lines = (tmp_path / "access.log").read_text().splitlines()
        assert any("service.test 200 " in line and line.endswith(" 1") for line in lines)
        assert any("service.test 429 " in line and line.endswith(" 0") for line in lines)
        (tmp_path / "ingress-evidence.json").write_text(
            json.dumps({"page": page, "limited_statuses": statuses, "sse": seen}, indent=2)
        )
    finally:
        if proc is not None and proc.poll() is None:
            proc.terminate()
            await asyncio.to_thread(proc.wait, 5)
        await h.stop()
