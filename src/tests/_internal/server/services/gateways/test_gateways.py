import shlex
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal import settings as core_settings
from dstack._internal.core.models.gateways import GatewayOTelConfig
from dstack._internal.proxy.gateway.const import SERVICE_SCALING_WINDOWS
from dstack._internal.proxy.gateway.schemas.stats import Stat
from dstack._internal.server.services import gateways
from dstack._internal.server.services.gateways import (
    _merge_per_window_stats,
    get_gateway_replica_models,
)
from dstack._internal.server.testing.common import (
    create_backend,
    create_gateway,
    create_gateway_replica,
    create_project,
    create_secret,
)


class TestMergePerWindowStats:
    def test_empty_returns_zero_stats(self):
        result = _merge_per_window_stats([])
        for window in SERVICE_SCALING_WINDOWS:
            assert result[window].requests == 0
            assert result[window].request_time == 0.0

    def test_single_replica_returns_same_values(self):
        stats = {w: Stat(requests=10, request_time=0.5) for w in SERVICE_SCALING_WINDOWS}
        result = _merge_per_window_stats([stats])
        for window in SERVICE_SCALING_WINDOWS:
            assert result[window].requests == 10
            assert result[window].request_time == pytest.approx(0.5)

    def test_multiple_replicas_sums_requests_and_averages_time(self):
        stats_a = {w: Stat(requests=10, request_time=1.0) for w in SERVICE_SCALING_WINDOWS}
        stats_b = {w: Stat(requests=30, request_time=3.0) for w in SERVICE_SCALING_WINDOWS}
        result = _merge_per_window_stats([stats_a, stats_b])
        for window in SERVICE_SCALING_WINDOWS:
            assert result[window].requests == 40
            assert result[window].request_time == pytest.approx(2.5)  # (10*1 + 30*3) / 40

    def test_zero_requests_across_all_replicas_returns_zero_time(self):
        stats_a = {w: Stat(requests=0, request_time=0.0) for w in SERVICE_SCALING_WINDOWS}
        stats_b = {w: Stat(requests=0, request_time=0.0) for w in SERVICE_SCALING_WINDOWS}
        result = _merge_per_window_stats([stats_a, stats_b])
        for window in SERVICE_SCALING_WINDOWS:
            assert result[window].requests == 0
            assert result[window].request_time == 0.0


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
class TestGetGatewayReplicaModels:
    async def test_new_style_returns_gateway_replicas(self, test_db, session: AsyncSession):
        project = await create_project(session=session)
        backend = await create_backend(session=session, project_id=project.id)
        gateway = await create_gateway(
            session=session, project_id=project.id, backend_id=backend.id
        )
        replica = await create_gateway_replica(
            session=session, gateway_id=gateway.id, backend=backend
        )
        await session.refresh(gateway, ["gateway_replicas", "gateway_replica"])
        result = get_gateway_replica_models(gateway)
        assert len(result) == 1
        assert result[0].id == replica.id

    async def test_old_style_returns_single_replica(self, test_db, session: AsyncSession):
        project = await create_project(session=session)
        backend = await create_backend(session=session, project_id=project.id)
        replica = await create_gateway_replica(session=session, backend=backend)
        gateway = await create_gateway(
            session=session, project_id=project.id, backend_id=backend.id
        )
        gateway.gateway_replica_id = replica.id
        await session.commit()
        await session.refresh(gateway, ["gateway_replicas", "gateway_replica"])
        result = get_gateway_replica_models(gateway)
        assert len(result) == 1
        assert result[0].id == replica.id

    async def test_no_replicas_returns_empty(self, test_db, session: AsyncSession):
        project = await create_project(session=session)
        backend = await create_backend(session=session, project_id=project.id)
        gateway = await create_gateway(
            session=session, project_id=project.id, backend_id=backend.id
        )
        await session.refresh(gateway, ["gateway_replicas", "gateway_replica"])
        result = get_gateway_replica_models(gateway)
        assert result == []


@pytest.mark.asyncio
class TestInitGateways:
    @pytest.mark.parametrize("target_version", ["0.22.2", "0.22.3"])
    async def test_release_version_controls_existing_gateway_update(
        self,
        session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
        gateway_update_sandbox: tuple[Path, Path, Mock],
        target_version: str,
    ):
        root, events_file, connection = gateway_update_sandbox
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        previously_updated_at = now - timedelta(minutes=2)
        monkeypatch.setattr(core_settings, "DSTACK_GATEWAY_PACKAGE_URL", None)
        monkeypatch.setattr(core_settings, "DSTACK_VERSION", target_version)
        monkeypatch.setattr(gateways.settings, "SKIP_GATEWAY_UPDATE", False)
        monkeypatch.setattr(gateways, "get_current_datetime", lambda: now)
        monkeypatch.setattr(
            gateways.gateway_connections_pool,
            "get_or_add",
            AsyncMock(return_value=connection),
        )
        monkeypatch.setattr(
            gateways.gateway_connections_pool,
            "all",
            AsyncMock(return_value=[connection]),
        )
        configure = AsyncMock()
        monkeypatch.setattr(gateways, "configure_gateway_replica", configure)
        project = await create_project(session=session)
        backend = await create_backend(session=session, project_id=project.id)
        replica = await create_gateway_replica(session=session, backend=backend)
        replica.app_updated_at = previously_updated_at
        await session.commit()

        await gateways.init_gateways(session)

        configure.assert_awaited_once()
        events = events_file.read_text().splitlines()
        if target_version == "0.22.2":
            assert events == ["blue pip show dstack"]
            assert (root / "version").read_text().strip() == "blue"
            assert replica.app_updated_at == previously_updated_at
            return

        assert (root / "version").read_text().strip() == "green"
        assert replica.app_updated_at == now
        install_package = f"green pip install dstack[gateway]=={target_version}"
        install_service = "green python -m dstack._internal.proxy.gateway.systemd install"
        reload_service = "systemctl daemon-reload active=green"
        restart_service = "systemctl restart dstack.gateway active=green"
        assert (
            events.index(install_package)
            < events.index(install_service)
            < events.index(reload_service)
            < events.index(restart_service)
        )

    async def test_configures_replicas_with_otel_settings(
        self, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ):
        connection = Mock(ip_address="1.1.1.1")
        monkeypatch.setattr(gateways.settings, "SKIP_GATEWAY_UPDATE", True)
        monkeypatch.setattr(
            gateways.gateway_connections_pool, "get_or_add", AsyncMock(return_value=connection)
        )
        monkeypatch.setattr(
            gateways.gateway_connections_pool, "all", AsyncMock(return_value=[connection])
        )
        configure = AsyncMock()
        monkeypatch.setattr(gateways, "configure_gateway_replica", configure)
        project = await create_project(session=session, name="main")
        backend = await create_backend(session=session, project_id=project.id)
        gateway = await create_gateway(
            session=session, project_id=project.id, backend_id=backend.id, name="my-gateway"
        )
        configuration = gateways.get_gateway_configuration(gateway)
        configuration.otel = GatewayOTelConfig(
            endpoint="https://otlp",
            headers={"Authorization": "Bearer ${{ secrets.token }}"},
            traces=True,
        )
        gateway.configuration = configuration.model_dump_json()
        await create_secret(session=session, project=project, name="token", value="s3cret")
        replica = await create_gateway_replica(
            session=session, backend=backend, gateway_id=gateway.id, replica_num=1
        )
        await session.commit()
        # Relationships must be loaded by init_gateways, not come from the identity map
        session.expunge_all()

        await gateways.init_gateways(session)

        configure.assert_awaited_once()
        assert configure.await_args is not None
        assert configure.await_args.args[0] is connection
        otel_settings = configure.await_args.args[1]
        assert otel_settings.traces_enabled
        assert otel_settings.headers == {"Authorization": "Bearer s3cret"}
        attributes = otel_settings.resource_attributes
        assert attributes["service.instance.id"] == str(replica.id)
        assert attributes["dstack.project.name"] == "main"
        assert attributes["dstack.gateway.name"] == "my-gateway"
        assert attributes["dstack.backend"] == backend.type.value


@pytest.fixture
def gateway_update_sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # Execute the real shell: mocking aexec would miss quoting, version gating, and the order
    # of service installation / venv switching / restart. Only the remote commands are stubbed;
    # no SSH, package installation, sudo, or real systemd operations are performed.
    root = tmp_path / "gateway root"
    root.mkdir()
    (root / "version").write_text("blue\n")
    events = tmp_path / "events"
    events.touch()
    for color in ("blue", "green"):
        venv_bin = root / color / "bin"
        venv_bin.mkdir(parents=True)
        for command in ("pip", "python"):
            _write_executable(
                venv_bin / command,
                f'printf "%s\\n" "{color} {command} $*" >> "$TEST_EVENTS"\n'
                + (
                    'if [ "$1" = show ]; then echo "Version: 0.22.2"; fi\n'
                    if command == "pip"
                    else ""
                ),
            )
    command_bin = tmp_path / "commands"
    command_bin.mkdir()
    _write_executable(
        command_bin / "sudo",
        'if [ "$1" = systemctl ]; then\n'
        '  printf "%s\\n" "$* active=$(cat "$TEST_ROOT/version")" >> "$TEST_EVENTS"\n'
        "else\n"
        '  exec "$@"\n'
        "fi\n",
    )
    # The only script substitution redirects its hard-coded remote root to this temporary dir.
    remote_root = "root=/home/ubuntu/dstack"
    assert gateways._GATEWAY_UPDATE_SCRIPT.count(remote_root) == 1
    monkeypatch.setattr(
        gateways,
        "_GATEWAY_UPDATE_SCRIPT",
        gateways._GATEWAY_UPDATE_SCRIPT.replace(remote_root, f"root={shlex.quote(str(root))}"),
    )

    def execute(command: str, timeout: float) -> str:
        return subprocess.run(
            shlex.split(command),
            check=True,
            capture_output=True,
            text=True,
            timeout=min(timeout, 5),
            env={
                "PATH": f"{command_bin}:/usr/bin:/bin",
                "TEST_EVENTS": str(events),
                "TEST_ROOT": str(root),
            },
        ).stdout

    connection = Mock(ip_address="1.1.1.1")
    connection.tunnel.aexec = AsyncMock(side_effect=execute)
    return root, events, connection


def _write_executable(path: Path, script: str):
    path.write_text("#!/bin/sh\nset -e\n" + script)
    path.chmod(0o755)
