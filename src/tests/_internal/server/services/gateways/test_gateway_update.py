import shlex
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal import settings as core_settings
from dstack._internal.server.services import gateways
from dstack._internal.server.testing.common import (
    create_backend,
    create_gateway_replica,
    create_project,
)


@pytest.mark.asyncio
class TestInitGateways:
    @pytest.mark.parametrize("target_version", ["0.22.2", "0.22.3"])
    async def test_release_version_controls_existing_gateway_update(
        self,
        session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
        gateway_update_sandbox: "_GatewayUpdateSandbox",
        target_version: str,
    ):
        sandbox = gateway_update_sandbox
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        previously_updated_at = now - timedelta(minutes=2)
        monkeypatch.setattr(core_settings, "DSTACK_GATEWAY_PACKAGE_URL", None)
        monkeypatch.setattr(core_settings, "DSTACK_VERSION", target_version)
        monkeypatch.setattr(gateways.settings, "SKIP_GATEWAY_UPDATE", False)
        monkeypatch.setattr(gateways, "get_current_datetime", lambda: now)
        monkeypatch.setattr(
            gateways.gateway_connections_pool,
            "get_or_add",
            AsyncMock(return_value=sandbox.connection),
        )
        monkeypatch.setattr(
            gateways.gateway_connections_pool,
            "all",
            AsyncMock(return_value=[sandbox.connection]),
        )
        configure = AsyncMock()
        monkeypatch.setattr(gateways, "configure_gateway_replica", configure)
        project = await create_project(session=session)
        backend = await create_backend(session=session, project_id=project.id)
        replica = await create_gateway_replica(session=session, backend=backend)
        replica.app_updated_at = previously_updated_at
        await session.commit()

        await gateways.init_gateways(session)

        configure.assert_awaited_once_with(sandbox.connection, attempts=7)
        events = sandbox.events.read_text().splitlines()
        if target_version == "0.22.2":
            assert events == ["blue pip show dstack"]
            assert (sandbox.root / "version").read_text().strip() == "blue"
            assert replica.app_updated_at == previously_updated_at
            return

        assert (sandbox.root / "version").read_text().strip() == "green"
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


@dataclass
class _GatewayUpdateSandbox:
    root: Path
    events: Path
    connection: Mock


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
    return _GatewayUpdateSandbox(root, events, connection)


def _write_executable(path: Path, script: str):
    path.write_text("#!/bin/sh\nset -e\n" + script)
    path.chmod(0o755)
