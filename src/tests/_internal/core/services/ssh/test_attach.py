import os
import shutil
import stat
import uuid
from pathlib import Path
from typing import Generator

import pytest

from dstack._internal.core.errors import SSHError
from dstack._internal.core.services.ssh import attach

pytestmark = pytest.mark.skipif(
    os.name != "posix" or not hasattr(os, "getuid"),
    reason="OpenSSH control sockets are only used on POSIX",
)


@pytest.fixture
def short_tmp_path() -> Generator[Path, None, None]:
    path = Path("/tmp") / f"dstack-test-{uuid.uuid4().hex[:8]}"
    path.mkdir(mode=0o700)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def test_base_attach_control_sock_path_uses_short_runtime_dir(
    monkeypatch: pytest.MonkeyPatch, short_tmp_path: Path
) -> None:
    monkeypatch.setattr(attach, "_CONTROL_SOCKET_BASE_DIR", short_tmp_path)
    dstack_ssh_dir = short_tmp_path / ("nested-" * 20) / ".dstack" / "ssh"

    class FakeConfigManager:
        def __init__(self) -> None:
            self.dstack_ssh_dir = dstack_ssh_dir

    monkeypatch.setattr(attach, "ConfigManager", FakeConfigManager)

    path = attach.BaseSSHAttach.get_control_sock_path("endpoint-with-a-very-long-name-" * 4)

    assert path.parent == short_tmp_path / f"dstack-ssh-{os.getuid()}"
    assert path.suffix == ".sock"
    assert not path.is_relative_to(dstack_ssh_dir)


def test_control_sock_path_uses_short_private_runtime_dir(
    monkeypatch: pytest.MonkeyPatch, short_tmp_path: Path
) -> None:
    monkeypatch.setattr(attach, "_CONTROL_SOCKET_BASE_DIR", short_tmp_path)
    dstack_ssh_dir = short_tmp_path / ("nested-" * 20) / ".dstack" / "ssh"
    run_name = "endpoint-with-a-very-long-name-" * 4

    path = attach._get_control_sock_path(dstack_ssh_dir, run_name)

    assert path == attach._get_control_sock_path(dstack_ssh_dir, run_name)
    assert path.parent == short_tmp_path / f"dstack-ssh-{os.getuid()}"
    assert path.suffix == ".sock"
    assert len(path.name) == attach._CONTROL_SOCKET_HASH_LENGTH + len(".sock")
    assert not path.is_relative_to(dstack_ssh_dir)
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700


def test_control_sock_path_separates_dstack_ssh_dirs(
    monkeypatch: pytest.MonkeyPatch, short_tmp_path: Path
) -> None:
    monkeypatch.setattr(attach, "_CONTROL_SOCKET_BASE_DIR", short_tmp_path)

    path1 = attach._get_control_sock_path(short_tmp_path / "home1" / ".dstack" / "ssh", "run")
    path2 = attach._get_control_sock_path(short_tmp_path / "home2" / ".dstack" / "ssh", "run")

    assert path1 != path2


def test_control_sock_path_falls_back_from_unsafe_runtime_dir(
    monkeypatch: pytest.MonkeyPatch, short_tmp_path: Path
) -> None:
    monkeypatch.setattr(attach, "_CONTROL_SOCKET_BASE_DIR", short_tmp_path)
    runtime_dir = short_tmp_path / f"dstack-ssh-{os.getuid()}"
    runtime_dir.mkdir()
    runtime_dir.chmod(0o755)

    legacy_path = short_tmp_path / ".dstack" / "ssh" / "run.control.sock"

    assert attach._get_control_sock_path(short_tmp_path / ".dstack" / "ssh", "run") == legacy_path


def test_control_sock_path_rejects_runtime_dir_symlink_and_falls_back(
    monkeypatch: pytest.MonkeyPatch, short_tmp_path: Path
) -> None:
    monkeypatch.setattr(attach, "_CONTROL_SOCKET_BASE_DIR", short_tmp_path)
    runtime_dir = short_tmp_path / f"dstack-ssh-{os.getuid()}"
    target_dir = short_tmp_path / "target"
    target_dir.mkdir()
    runtime_dir.symlink_to(target_dir)

    legacy_path = short_tmp_path / ".dstack" / "ssh" / "run.control.sock"

    assert attach._get_control_sock_path(short_tmp_path / ".dstack" / "ssh", "run") == legacy_path


def test_control_sock_path_falls_back_when_short_base_dir_is_unavailable(
    monkeypatch: pytest.MonkeyPatch, short_tmp_path: Path
) -> None:
    monkeypatch.setattr(attach, "_CONTROL_SOCKET_BASE_DIR", short_tmp_path / "missing")
    legacy_path = short_tmp_path / ".dstack" / "ssh" / "run.control.sock"

    assert attach._get_control_sock_path(short_tmp_path / ".dstack" / "ssh", "run") == legacy_path


def test_control_sock_path_falls_back_when_short_path_is_too_long(
    monkeypatch: pytest.MonkeyPatch, short_tmp_path: Path
) -> None:
    long_base_dir = short_tmp_path / ("nested-" * 20)
    long_base_dir.mkdir()
    monkeypatch.setattr(attach, "_CONTROL_SOCKET_BASE_DIR", long_base_dir)
    legacy_path = short_tmp_path / ".dstack" / "ssh" / "run.control.sock"

    assert attach._get_control_sock_path(short_tmp_path / ".dstack" / "ssh", "run") == legacy_path


def test_control_sock_path_reports_short_and_fallback_failures(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(attach, "_CONTROL_SOCKET_BASE_DIR", tmp_path / "missing")
    dstack_ssh_dir = tmp_path / ("nested-" * 20) / ".dstack" / "ssh"

    with pytest.raises(SSHError) as exc_info:
        attach._get_control_sock_path(dstack_ssh_dir, "endpoint-with-a-very-long-name-" * 4)
    error = str(exc_info.value)
    assert "short path failed" in error
    assert "fallback path failed" in error
    assert "Cannot access SSH control socket base directory" in error
    assert "is too long for an SSH control socket" in error


def test_control_sock_path_rejects_runtime_dir_symlink(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, short_tmp_path: Path
) -> None:
    monkeypatch.setattr(attach, "_CONTROL_SOCKET_BASE_DIR", short_tmp_path)
    runtime_dir = short_tmp_path / f"dstack-ssh-{os.getuid()}"
    target_dir = short_tmp_path / "target"
    target_dir.mkdir()
    runtime_dir.symlink_to(target_dir)
    dstack_ssh_dir = tmp_path / ("nested-" * 20) / ".dstack" / "ssh"

    with pytest.raises(SSHError, match="not a directory"):
        attach._get_control_sock_path(dstack_ssh_dir, "endpoint-with-a-very-long-name-" * 4)
