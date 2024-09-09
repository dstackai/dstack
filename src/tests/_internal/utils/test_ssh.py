import subprocess
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from dstack._internal.utils.ssh import SSHClientInfo, check_required_ssh_version


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


class TestSSHClientInfo:
    def test_openbsd(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr("dstack._internal.utils.ssh.IS_WINDOWS", False)
        path = Path("/usr/bin/ssh")
        info = SSHClientInfo.from_raw_version("OpenSSH_9.7, LibreSSL 3.9.0", path)
        assert info == SSHClientInfo(
            path=path,
            version="9.7",
            version_tuple=(9, 7),
            for_windows=False,
            supports_control_socket=True,
            supports_multiplexing=True,
            supports_background_mode=True,
        )

    def test_linux(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr("dstack._internal.utils.ssh.IS_WINDOWS", False)
        path = Path("/usr/bin/ssh")
        info = SSHClientInfo.from_raw_version(
            "OpenSSH_9.2p1 Debian-2+deb12u3, OpenSSL 3.0.13 30 Jan 2024", path
        )
        assert info == SSHClientInfo(
            path=path,
            version="9.2p1",
            version_tuple=(9, 2),
            for_windows=False,
            supports_control_socket=True,
            supports_multiplexing=True,
            supports_background_mode=True,
        )

    def test_macos(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr("dstack._internal.utils.ssh.IS_WINDOWS", False)
        path = Path("/usr/bin/ssh")
        info = SSHClientInfo.from_raw_version("OpenSSH_9.7p1, LibreSSL 3.3.6", path)
        assert info == SSHClientInfo(
            path=path,
            version="9.7p1",
            version_tuple=(9, 7),
            for_windows=False,
            supports_control_socket=True,
            supports_multiplexing=True,
            supports_background_mode=True,
        )

    def test_windows_msys2(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr("dstack._internal.utils.ssh.IS_WINDOWS", True)
        path = Path("C:\\Program Files\\Git\\usr\\bin\\ssh.exe")
        info = SSHClientInfo.from_raw_version("OpenSSH_9.8p1, OpenSSL 3.2.2 4 Jun 2024", path)
        assert info == SSHClientInfo(
            path=path,
            version="9.8p1",
            version_tuple=(9, 8),
            for_windows=False,
            supports_control_socket=True,
            supports_multiplexing=False,
            supports_background_mode=True,
        )

    def test_windows_for_windows(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr("dstack._internal.utils.ssh.IS_WINDOWS", True)
        path = Path("C:\\Windows\\System32\\OpenSSH\\ssh.exe")
        info = SSHClientInfo.from_raw_version("OpenSSH_for_Windows_8.6p1, LibreSSL 3.4.3", path)
        assert info == SSHClientInfo(
            path=path,
            version="8.6p1",
            version_tuple=(8, 6),
            for_windows=True,
            supports_control_socket=False,
            supports_multiplexing=False,
            supports_background_mode=False,
        )
