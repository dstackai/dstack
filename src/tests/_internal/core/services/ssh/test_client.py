from pathlib import Path

import pytest

from dstack._internal.core.services.ssh.client import SSHClientInfo


class TestSSHClientInfo:
    def test_openbsd(self):
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

    def test_linux(self):
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

    def test_macos(self):
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

    @pytest.mark.windows_only
    def test_windows_msys2(self):
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

    @pytest.mark.windows_only
    def test_windows_for_windows(self):
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
