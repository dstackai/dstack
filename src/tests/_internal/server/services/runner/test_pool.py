from pathlib import Path

import pytest

from dstack._internal.server.services.runner import pool as runner_pool
from dstack._internal.server.services.runner.pool import InstanceConnection


class TestInstanceConnectionCreateConnDir:
    def test_retries_if_directory_disappears_during_creation(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        conn_dir = tmp_path / "connection"
        original_mkdir = Path.mkdir
        attempts = 0

        def racing_mkdir(path: Path, *args, **kwargs):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise FileExistsError(path)
            return original_mkdir(path, *args, **kwargs)

        monkeypatch.setattr(Path, "mkdir", racing_mkdir)

        InstanceConnection._create_conn_dir(conn_dir)

        assert attempts == 2
        assert conn_dir.is_dir()

    def test_preserves_file_conflict(self, tmp_path: Path):
        conn_dir = tmp_path / "connection"
        conn_dir.write_text("not a directory")

        with pytest.raises(FileExistsError):
            InstanceConnection._create_conn_dir(conn_dir)

        assert conn_dir.read_text() == "not a directory"

    def test_limits_retries(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        conn_dir = tmp_path / "connection"
        attempts = 0

        def racing_mkdir(path: Path, *args, **kwargs):
            nonlocal attempts
            attempts += 1
            raise FileExistsError(path)

        monkeypatch.setattr(Path, "mkdir", racing_mkdir)

        with pytest.raises(FileExistsError):
            InstanceConnection._create_conn_dir(conn_dir)

        assert attempts == runner_pool._CONN_DIR_CREATE_ATTEMPTS


def test_instance_connections_dir_is_isolated_from_server_state():
    assert runner_pool.CONNECTIONS_DIR != runner_pool.SERVER_DIR_PATH / "instance-connections"
    assert runner_pool.CONNECTIONS_DIR.is_dir()
