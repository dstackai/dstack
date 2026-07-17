import subprocess
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from dstack._internal.compat import IS_WINDOWS
from dstack._internal.utils.path import FilePath
from dstack._internal.utils.ssh import (
    check_required_ssh_version,
    include_ssh_config,
    normalize_path,
    update_ssh_config,
)

pytestmark = pytest.mark.windows


class TestNormalizePath:
    @pytest.mark.skipif(IS_WINDOWS, reason="POSIX OpenSSH home semantics")
    def test_does_not_collapse_path_under_overridden_home(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        identity_file = tmp_path / ".dstack" / "ssh" / "key"

        assert normalize_path(identity_file, collapse_user=True) == str(identity_file)

    @pytest.mark.skipif(IS_WINDOWS, reason="POSIX OpenSSH home semantics")
    def test_does_not_collapse_path_without_passwd_entry(self, tmp_path, monkeypatch):
        monkeypatch.setattr("pwd.getpwuid", MagicMock(side_effect=KeyError))
        identity_file = tmp_path / ".dstack" / "ssh" / "key"

        assert normalize_path(identity_file, collapse_user=True) == str(identity_file)

    def test_collapses_path_under_openssh_home(self):
        identity_file = Path.home() / ".dstack" / "ssh" / "key"

        assert normalize_path(identity_file, collapse_user=True) == "~/.dstack/ssh/key"


@pytest.mark.skipif(IS_WINDOWS, reason="POSIX OpenSSH home semantics")
class TestTemporaryHomeSSHConfig:
    def test_writes_absolute_identity_file(self, tmp_path, monkeypatch):
        home = tmp_path / "home"
        monkeypatch.setenv("HOME", str(home))
        identity_file = home / ".dstack" / "ssh" / "key"
        config_file = home / ".dstack" / "ssh" / "config"

        update_ssh_config(
            config_file,
            "test-run",
            {"IdentityFile": FilePath(identity_file)},
        )

        assert f"    IdentityFile {identity_file}\n" in config_file.read_text()

    def test_writes_absolute_include(self, tmp_path, monkeypatch):
        home = tmp_path / "home"
        monkeypatch.setenv("HOME", str(home))
        dstack_config = home / ".dstack" / "ssh" / "config"
        user_config = home / ".ssh" / "config"
        user_config.parent.mkdir(mode=0o700, parents=True)

        include_ssh_config(dstack_config, user_config)

        assert user_config.read_text() == f"Include {dstack_config}\n"


class TestCheckRequiredSSHVersion(unittest.TestCase):
    @patch("subprocess.run")
    def test_ssh_version_above_8_4(self, mock_run):
        # Mock subprocess.run to return a version above 8.4
        mock_run.return_value = MagicMock(returncode=0, stderr="OpenSSH_8.6p1, LibreSSL 3.3.6")

        self.assertTrue(check_required_ssh_version())

    @patch("subprocess.run")
    def test_ssh_version_below_8_4(self, mock_run):
        # Mock subprocess.run to return version 8.4
        mock_run.return_value = MagicMock(returncode=0, stderr="OpenSSH_8.2p1, LibreSSL 3.2.3")

        self.assertFalse(check_required_ssh_version())

    @patch("subprocess.run")
    def test_subprocess_error(self, mock_run):
        # Mock subprocess.run to raise a CalledProcessError
        mock_run.side_effect = subprocess.CalledProcessError(returncode=1, cmd="ssh -V")

        self.assertFalse(check_required_ssh_version())

    @patch("subprocess.run")
    def test_ssh_version_on_windows_above_8_4(self, mock_run):
        # Mock subprocess.run to return version 8.4
        mock_run.return_value = MagicMock(
            returncode=0, stdout="OpenSSH_for_Windows_8.7p1, LibreSSL 3.2.3", stderr=""
        )

        self.assertTrue(check_required_ssh_version())

    @patch("subprocess.run")
    def test_ssh_version_on_windows_below_8_4(self, mock_run):
        # Mock subprocess.run to return version 8.4
        mock_run.return_value = MagicMock(
            returncode=0, stdout="OpenSSH_for_Windows_8.1p1, LibreSSL 3.2.3", stderr=""
        )

        self.assertFalse(check_required_ssh_version())
