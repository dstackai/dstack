"""Separate Gateway process and deterministic backend; test control uses private Unix IPC."""

import argparse
import asyncio
import contextvars
import json
import os
import resource
import socket
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import httpx2
import uvicorn

from dstack._internal.proxy.gateway import app as gateway_app
from dstack._internal.proxy.gateway.auth import GatewayProxyAuthProvider
from dstack._internal.proxy.gateway.deps import GatewayDependencyInjector
from dstack._internal.proxy.gateway.models import GlobalProxyConfig
from dstack._internal.proxy.gateway.repo.repo import GatewayProxyRepo
from dstack._internal.proxy.gateway.services.metering import Clock, MeteringCollector
from dstack._internal.proxy.gateway.services.metering_store import MeteringStore
from dstack._internal.proxy.gateway.services.nginx import Nginx
from dstack._internal.proxy.gateway.services.stats import StatsCollector
from dstack._internal.proxy.lib.models import ChatModel, OpenAIChatModelFormat
from dstack._internal.proxy.lib.routers import model_proxy
from dstack._internal.proxy.lib.services.usage import VLLM_PROFILE
from dstack._internal.proxy.lib.testing.common import make_service
from tests._internal.proxy.gateway.metering.backend import make_backend

REQUEST_ID = contextvars.ContextVar("test_request_id", default="")


class TestClock(Clock):
    def __init__(self, value: str):
        self.now = datetime.fromisoformat(value)

    def utc_now(self):
        return self.now


class TracingCollector(MeteringCollector):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.completed: dict[str, asyncio.Event] = {}
        self.request_ids = {}
        self.checkpoint_seconds = []

    def start_attempt(self, key, profile):
        attempt = super().start_attempt(key, profile)
        self.request_ids[attempt] = REQUEST_ID.get()
        return attempt

    async def _finish(self, attempt):
        await super()._finish(attempt)
        if attempt.finished:
            self.completed.setdefault(self.request_ids.pop(attempt, ""), asyncio.Event()).set()

    async def _save(self, state):
        started = time.perf_counter()
        await super()._save(state)
        self.checkpoint_seconds.append(time.perf_counter() - started)


class TestNginx(Nginx):
    def write_global_conf(self):
        pass

    async def drain(self) -> bool:
        # This harness forwards directly to its fixture backend and owns no Nginx workers.
        return True


async def _noop(*args, **kwargs):
    pass


async def _worker(args) -> None:
    http_clients = []
    collector = None
    if args.kind == "backend":
        app = make_backend()
    else:
        repo = GatewayProxyRepo()
        for name, service_id in [("a", "a" * 32), ("b", "b" * 32)]:
            await repo.set_service(make_service("p", f"run-{name}", run_id=service_id))
            await repo.set_model(
                ChatModel(
                    project_name="p",
                    name=f"model-{name}",
                    run_name=f"run-{name}",
                    created_at=datetime.now(timezone.utc),
                    format_spec=OpenAIChatModelFormat(format="openai", prefix="/v1"),
                )
            )
        await repo.set_config(
            GlobalProxyConfig(
                usage_metering_profiles={"a" * 32: VLLM_PROFILE, "b" * 32: VLLM_PROFILE}
            )
        )
        clock = Clock() if args.realtime else TestClock(args.clock)
        store = MeteringStore(Path(args.state) / "usage-counters.json")
        collector = TracingCollector(store, clock=clock)
        app = gateway_app.make_app(repo=repo, nginx=TestNginx(), metering_store=store, clock=clock)
        auth_client = httpx2.AsyncClient(base_url=args.backend, timeout=10)
        backend_client = httpx.AsyncClient(
            base_url=args.nginx_url or args.backend,
            headers={"Host": "service.test"} if args.nginx_url else {},
            timeout=30,
        )
        http_clients = [auth_client, backend_client]
        app.state.proxy_dependency_injector = GatewayDependencyInjector(
            repo=repo,
            auth=GatewayProxyAuthProvider(auth_client),
            nginx=TestNginx(),
            stats_collector=StatsCollector(Path(args.state) / "unused-access.log"),
            metering=collector,
        )
        gateway_app.apply_all = _noop

        async def connection(*args, **kwargs):
            return backend_client

        model_proxy.get_service_replica_client = connection

        @app.middleware("http")
        async def trace(request, call_next):
            token = REQUEST_ID.set(request.headers.get("X-Test-Request-ID", ""))
            try:
                return await call_next(request)
            finally:
                REQUEST_ID.reset(token)

    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host="127.0.0.1",
            port=0,
            log_level="warning",
            access_log=False,
            timeout_graceful_shutdown=2,
        )
    )
    ipc_server = None
    loop_lag = []

    async def sample_lag():
        while True:
            before = time.perf_counter()
            await asyncio.sleep(0.01)
            loop_lag.append(max(0, time.perf_counter() - before - 0.01))

    lag_task = asyncio.create_task(sample_lag())
    if collector is not None:

        async def control(reader, writer):
            try:
                request = json.loads(await reader.readline())
                if request["op"] == "advance":
                    if args.realtime:
                        raise ValueError("Real clock cannot be advanced")
                    assert isinstance(collector.clock, TestClock)
                    collector.clock.now += timedelta(seconds=request.get("seconds", 60))
                    await collector.rotate_if_due()
                elif request["op"] == "wait":
                    await asyncio.wait_for(
                        collector.completed.setdefault(request["id"], asyncio.Event()).wait(), 10
                    )
                elif request["op"] == "checkpoint":
                    await collector.checkpoint()
                result: dict = {"now": collector.clock.utc_now().isoformat()}
                if request["op"] == "metrics":
                    result.update(
                        loop_lag_seconds=loop_lag[-10000:],
                        checkpoint_seconds=collector.checkpoint_seconds[-10000:],
                        peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                        * (1 if sys.platform == "darwin" else 1024),
                    )
            except Exception as exc:
                result = {"error": repr(exc)}
            writer.write(json.dumps(result).encode() + b"\n")
            await writer.drain()
            writer.close()
            await writer.wait_closed()

        ipc_server = await asyncio.start_unix_server(control, path=args.ipc)
    sockets = None
    if args.kind == "backend":
        tcp = socket.socket()
        tcp.bind(("127.0.0.1", 0))
        tcp.setblocking(False)
        unix = socket.socket(socket.AF_UNIX)
        unix.bind(args.backend_socket)
        unix.setblocking(False)
        sockets = [tcp, unix]
    serving = asyncio.create_task(server.serve(sockets=sockets))
    try:
        while not server.started:
            if serving.done():
                await serving
                raise RuntimeError("Server stopped before readiness")
            await asyncio.sleep(0.01)
        port = server.servers[0].sockets[0].getsockname()[1]
        Path(args.ready).write_text(json.dumps({"port": port}))
        await serving
    finally:
        lag_task.cancel()
        await asyncio.gather(lag_task, return_exceptions=True)
        if ipc_server:
            ipc_server.close()
            await ipc_server.wait_closed()
        for client in http_clients:
            await client.aclose()


class Harness:
    def __init__(self, state: Path, realtime: bool = False, nginx_url: str = ""):
        self.nginx_url = nginx_url
        self.audit = []
        self.state = state
        self.realtime = realtime
        self.now = datetime(2026, 11, 16, 10, tzinfo=timezone.utc)
        self._ipc_dir = tempfile.TemporaryDirectory(prefix="ds2-", dir=tempfile.gettempdir())
        self.ipc = Path(self._ipc_dir.name) / "control.sock"
        self.backend_socket = Path(self._ipc_dir.name) / "backend.sock"
        self.workers = {}
        self.gateway_url = ""
        self.backend_url = ""

    async def start(self) -> None:
        self.state.mkdir(parents=True, exist_ok=True)
        try:
            self.backend_url = await self._launch("backend")
            self.gateway_url = await self._launch("gateway")
        except BaseException:
            await self.stop()
            raise

    async def _launch(self, kind: str) -> str:
        ready = self.state / f"{kind}.ready.json"
        ready.unlink(missing_ok=True)
        if kind == "gateway":
            self.ipc.unlink(missing_ok=True)
        command = [
            sys.executable,
            "-m",
            __name__
            if __name__ != "__main__"
            else "tests._internal.proxy.gateway.metering.harness",
            "--kind",
            kind,
            "--state",
            str(self.state),
            "--ready",
            str(ready),
            "--ipc",
            str(self.ipc),
            "--clock",
            self.now.isoformat(),
        ]
        command += ["--backend-socket", str(self.backend_socket), "--nginx-url", self.nginx_url]
        if self.backend_url:
            command += ["--backend", self.backend_url]
        if self.realtime:
            command += ["--realtime"]
        log = (self.state / f"{kind}.log").open("ab")
        env = dict(os.environ)
        env["PYTHONPATH"] = (
            str(Path(__file__).resolve().parents[5]) + os.pathsep + env.get("PYTHONPATH", "")
        )
        proc = subprocess.Popen(
            command, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, env=env
        )
        self.workers[kind] = (proc, log)
        deadline = time.monotonic() + 25
        async with httpx.AsyncClient(timeout=1) as client:
            while time.monotonic() < deadline:
                if proc.poll() is not None:
                    raise RuntimeError(
                        f"{kind} exited: " + (self.state / f"{kind}.log").read_text()[-4000:]
                    )
                try:
                    url = f"http://127.0.0.1:{json.loads(ready.read_text())['port']}"
                    response = await client.get(url + "/")
                    if response.status_code == 200:
                        return url
                except (OSError, ValueError, httpx.HTTPError):
                    pass
                await asyncio.sleep(0.02)
        raise TimeoutError(f"{kind} readiness timed out")

    async def ipc_command(self, op: str, **kwargs) -> dict:
        reader, writer = await asyncio.open_unix_connection(self.ipc)
        try:
            writer.write(json.dumps({"op": op, **kwargs}).encode() + b"\n")
            await writer.drain()
            result = json.loads(await asyncio.wait_for(reader.readline(), 15))
            if "error" in result:
                raise RuntimeError(result["error"])
            self.audit.append({"control": {"op": op, **kwargs}, "result": result})
            return result
        finally:
            writer.close()
            await writer.wait_closed()

    async def advance_clock(self, seconds: int = 60) -> None:
        result = await self.ipc_command("advance", seconds=seconds)
        self.now = datetime.fromisoformat(result["now"])

    async def wait_finalized(self, request_id: str) -> None:
        await self.ipc_command("wait", id=request_id)

    async def batches(self, limit: int = 100) -> dict:
        async with httpx.AsyncClient(base_url=self.gateway_url, timeout=10) as client:
            response = await client.get("/api/usage/batches", params={"limit": limit})
            response.raise_for_status()
            result = response.json()
            self.audit.append({"batches": result})
            return result

    async def backend_control(self, **body) -> dict:
        async with httpx.AsyncClient(base_url=self.backend_url, timeout=10) as client:
            response = await client.post("/test/control", json=body)
            response.raise_for_status()
            return response.json()

    async def wait_backend_started(self, request_id: str) -> None:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if request_id in (await self.backend_control())["started"]:
                return
            await asyncio.sleep(0.01)
        raise TimeoutError(f"{request_id} did not start")

    async def restart(self, kill: bool = False) -> None:
        await self._stop_worker("gateway", kill=kill)
        self.gateway_url = await self._launch("gateway")

    async def _stop_worker(self, kind: str, kill: bool = False) -> None:
        if kind not in self.workers:
            return
        proc, log = self.workers.pop(kind)
        try:
            if proc.poll() is None:
                proc.kill() if kill else proc.terminate()
                try:
                    await asyncio.to_thread(proc.wait, 8)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    await asyncio.to_thread(proc.wait, 5)
        finally:
            log.close()

    async def stop(self) -> None:
        if self.state.exists():
            (self.state / "audit.json").write_text(json.dumps(self.audit, indent=2))
        for kind in list(self.workers):
            await self._stop_worker(kind)
        self._ipc_dir.cleanup()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=["gateway", "backend"], required=True)
    parser.add_argument("--state", required=True)
    parser.add_argument("--ready", required=True)
    parser.add_argument("--ipc", required=True)
    parser.add_argument("--clock", required=True)
    parser.add_argument("--backend", default="")
    parser.add_argument("--backend-socket", required=True)
    parser.add_argument("--nginx-url", default="")
    parser.add_argument("--realtime", action="store_true")
    asyncio.run(_worker(parser.parse_args()))


if __name__ == "__main__":
    main()
