import re
from pathlib import Path

from dstack._internal.core.models.instances import SSHConnectionParams
from dstack._internal.core.services.ssh.tunnel import (
    SocketPair,
    SSHTunnel,
    TCPSocket,
    UnixSocket,
    ports_to_forwarded_sockets,
)
from dstack._internal.utils.path import FileContent, FilePath

SAMPLE_TUNNEL_WITH_ALL_PARAMS = SSHTunnel(
    destination="ubuntu@my-server",
    identity=FilePath("/home/user/.ssh/id_rsa"),
    control_sock_path="/tmp/control.sock",
    options={"Opt1": "opt1"},
    ssh_config_path="/home/user/.ssh/config",
    port=10022,
    ssh_proxy=SSHConnectionParams(hostname="proxy", username="test", port=10022),
    forwarded_sockets=[SocketPair(UnixSocket("/1"), UnixSocket("/2"))],
    reverse_forwarded_sockets=[SocketPair(UnixSocket("/1"), UnixSocket("/2"))],
)


class TestSSHTunnel:
    def test_open_command_basic(self) -> None:
        tunnel = SSHTunnel(
            destination="ubuntu@my-server",
            identity=FilePath("/home/user/.ssh/id_rsa"),
            control_sock_path="/tmp/control.sock",
            options={
                "Opt1": "opt1",
                "Opt2": "opt2",
            },
            ssh_config_path="/home/user/.ssh/config",
            port=10022,
        )
        assert " ".join(tunnel.open_command()) == (
            "ssh"
            " -F /home/user/.ssh/config"
            " -f -N -M"
            " -S /tmp/control.sock"
            " -i /home/user/.ssh/id_rsa"
            " -p 10022"
            " -o Opt1=opt1"
            " -o Opt2=opt2"
            " ubuntu@my-server"
        )

    def test_open_command_with_temp_identity_file(self) -> None:
        tunnel = SSHTunnel(
            destination="ubuntu@my-server",
            identity=FileContent("my private key"),
            control_sock_path="/tmp/control.sock",
            options={},
        )
        command = " ".join(tunnel.open_command())
        match = re.fullmatch(
            r"ssh -F none -f -N -M -S /tmp/control.sock -i (\S+) ubuntu@my-server", command
        )
        assert match
        assert Path(match.group(1)).read_text() == "my private key"

    def test_open_command_with_temp_control_socket(self) -> None:
        tunnel = SSHTunnel(
            destination="ubuntu@my-server",
            identity=FilePath("/home/user/.ssh/id_rsa"),
            options={},
        )
        command = " ".join(tunnel.open_command())
        assert re.fullmatch(
            r"ssh -F none -f -N -M -S \S+ -i /home/user/.ssh/id_rsa ubuntu@my-server", command
        )

    def test_open_command_with_proxy(self) -> None:
        tunnel = SSHTunnel(
            destination="ubuntu@my-server",
            identity=FilePath("/home/user/.ssh/id_rsa"),
            control_sock_path="/tmp/control.sock",
            options={},
            ssh_proxy=SSHConnectionParams(hostname="proxy", username="test", port=10022),
        )
        assert tunnel.open_command() == [
            "ssh",
            "-F",
            "none",
            "-f",
            "-N",
            "-M",
            "-S",
            "/tmp/control.sock",
            "-i",
            "/home/user/.ssh/id_rsa",
            "-o",
            (
                "ProxyCommand="
                "ssh -i /home/user/.ssh/id_rsa -W %h:%p -o StrictHostKeyChecking=no"
                " -o UserKnownHostsFile=/dev/null -p 10022 test@proxy"
            ),
            "ubuntu@my-server",
        ]

    def test_open_command_with_forwarding(self) -> None:
        tunnel = SSHTunnel(
            destination="ubuntu@my-server",
            identity=FilePath("/home/user/.ssh/id_rsa"),
            control_sock_path="/tmp/control.sock",
            options={},
            forwarded_sockets=[
                SocketPair(local=UnixSocket("/tmp/80"), remote=TCPSocket("localhost", 80)),
                SocketPair(local=TCPSocket("127.0.0.1", 8000), remote=TCPSocket("::1", 80)),
            ],
            reverse_forwarded_sockets=[
                SocketPair(local=UnixSocket("/tmp/local"), remote=UnixSocket("/tmp/remote")),
                SocketPair(local=TCPSocket("test.local", 80), remote=TCPSocket("localhost", 8000)),
            ],
        )
        assert " ".join(tunnel.open_command()) == (
            "ssh"
            " -F none"
            " -f -N -M"
            " -S /tmp/control.sock"
            " -i /home/user/.ssh/id_rsa"
            " -L /tmp/80:localhost:80"
            " -L 127.0.0.1:8000:[::1]:80"
            " -R /tmp/remote:/tmp/local"
            " -R localhost:8000:test.local:80"
            " ubuntu@my-server"
        )

    def test_check_command(self) -> None:
        command = SAMPLE_TUNNEL_WITH_ALL_PARAMS.check_command()
        assert command == ["ssh", "-S", "/tmp/control.sock", "-O", "check", "ubuntu@my-server"]

    def test_close_command(self) -> None:
        command = SAMPLE_TUNNEL_WITH_ALL_PARAMS.close_command()
        assert command == ["ssh", "-S", "/tmp/control.sock", "-O", "exit", "ubuntu@my-server"]

    def test_exec_command(self) -> None:
        command = SAMPLE_TUNNEL_WITH_ALL_PARAMS.exec_command()
        assert command == ["ssh", "-S", "/tmp/control.sock", "ubuntu@my-server"]


def test_ports_to_forwarded_sockets() -> None:
    assert ports_to_forwarded_sockets({80: 8000, 22: 2200}, bind_local="::1") == [
        SocketPair(local=TCPSocket("::1", 8000), remote=TCPSocket("localhost", 80)),
        SocketPair(local=TCPSocket("::1", 2200), remote=TCPSocket("localhost", 22)),
    ]
