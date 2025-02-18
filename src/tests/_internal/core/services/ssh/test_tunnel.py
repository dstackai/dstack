from pathlib import Path

import pytest

from dstack._internal.core.models.instances import SSHConnectionParams
from dstack._internal.core.services.ssh.client import SSHClientInfo
from dstack._internal.core.services.ssh.tunnel import (
    IPSocket,
    SocketPair,
    SSHTunnel,
    UnixSocket,
    ports_to_forwarded_sockets,
)
from dstack._internal.utils.path import FileContent, FilePath


class TestSSHTunnel:
    @pytest.fixture
    def ssh_client_info(self, monkeypatch: pytest.MonkeyPatch) -> SSHClientInfo:
        ssh_client_info = SSHClientInfo.from_raw_version("OpenSSH_9.7p1", Path("/usr/bin/ssh"))
        monkeypatch.setattr(
            "dstack._internal.core.services.ssh.client._ssh_client_info", ssh_client_info
        )
        return ssh_client_info

    @pytest.fixture
    def sample_tunnel_with_all_params(self, ssh_client_info: SSHClientInfo) -> SSHTunnel:
        return SSHTunnel(
            destination="ubuntu@my-server",
            identity=FilePath("/home/user/.ssh/id_rsa"),
            control_sock_path="/tmp/control.sock",
            options={"Opt1": "opt1"},
            ssh_config_path="/home/user/.ssh/config",
            port=10022,
            ssh_proxies=[
                (SSHConnectionParams(hostname="proxy", username="test", port=10022), None)
            ],
            forwarded_sockets=[SocketPair(UnixSocket("/1"), UnixSocket("/2"))],
            reverse_forwarded_sockets=[SocketPair(UnixSocket("/1"), UnixSocket("/2"))],
        )

    @pytest.mark.usefixtures("ssh_client_info")
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
            "/usr/bin/ssh"
            " -F /home/user/.ssh/config"
            " -i /home/user/.ssh/id_rsa"
            f" -E {tunnel.temp_dir.name}/tunnel.log"
            " -N -f"
            " -o ControlMaster=auto"
            " -S /tmp/control.sock"
            " -p 10022"
            " -o Opt1=opt1"
            " -o Opt2=opt2"
            " ubuntu@my-server"
        )

    @pytest.mark.usefixtures("ssh_client_info")
    def test_open_command_with_temp_identity_file(self) -> None:
        tunnel = SSHTunnel(
            destination="ubuntu@my-server",
            identity=FileContent("my private key"),
            control_sock_path="/tmp/control.sock",
            options={},
        )
        temp_dir = tunnel.temp_dir.name
        assert " ".join(tunnel.open_command()) == (
            "/usr/bin/ssh"
            " -F none"
            f" -i {temp_dir}/identity"
            f" -E {temp_dir}/tunnel.log"
            " -N -f"
            " -o ControlMaster=auto"
            " -S /tmp/control.sock"
            " ubuntu@my-server"
        )
        assert (Path(temp_dir) / "identity").read_text() == "my private key"

    @pytest.mark.usefixtures("ssh_client_info")
    def test_open_command_with_temp_control_socket(self) -> None:
        tunnel = SSHTunnel(
            destination="ubuntu@my-server",
            identity=FilePath("/home/user/.ssh/id_rsa"),
            options={},
        )
        temp_dir = tunnel.temp_dir.name
        assert " ".join(tunnel.open_command()) == (
            "/usr/bin/ssh"
            " -F none"
            " -i /home/user/.ssh/id_rsa"
            f" -E {temp_dir}/tunnel.log"
            " -N -f"
            " -o ControlMaster=auto"
            f" -S {temp_dir}/control.sock"
            " ubuntu@my-server"
        )

    @pytest.mark.usefixtures("ssh_client_info")
    def test_open_command_with_one_proxy(self) -> None:
        tunnel = SSHTunnel(
            destination="ubuntu@my-server",
            identity=FilePath("/home/user/.ssh/id_rsa"),
            control_sock_path="/tmp/control.sock",
            options={},
            ssh_proxies=[
                (
                    SSHConnectionParams(hostname="proxy", username="test", port=10022),
                    FilePath("/home/user/.ssh/proxy"),
                )
            ],
        )
        assert tunnel.open_command() == [
            "/usr/bin/ssh",
            "-F",
            "none",
            "-i",
            "/home/user/.ssh/id_rsa",
            "-E",
            f"{tunnel.temp_dir.name}/tunnel.log",
            "-N",
            "-f",
            "-o",
            "ControlMaster=auto",
            "-S",
            "/tmp/control.sock",
            "-o",
            (
                "ProxyCommand="
                "/usr/bin/ssh -i /home/user/.ssh/proxy -W %h:%p -o StrictHostKeyChecking=no"
                " -o UserKnownHostsFile=/dev/null -p 10022 test@proxy"
            ),
            "ubuntu@my-server",
        ]

    @pytest.mark.usefixtures("ssh_client_info")
    def test_open_command_with_two_proxies(self) -> None:
        tunnel = SSHTunnel(
            destination="ubuntu@my-server",
            identity=FilePath("/home/user/.ssh/id_rsa"),
            control_sock_path="/tmp/control.sock",
            options={},
            ssh_proxies=[
                (
                    SSHConnectionParams(hostname="proxy1", username="test1", port=10022),
                    None,
                ),
                (
                    SSHConnectionParams(hostname="proxy2", username="test2", port=20022),
                    FilePath("/home/user/.ssh/proxy2"),
                ),
            ],
        )
        assert tunnel.open_command() == [
            "/usr/bin/ssh",
            "-F",
            "none",
            "-i",
            "/home/user/.ssh/id_rsa",
            "-E",
            f"{tunnel.temp_dir.name}/tunnel.log",
            "-N",
            "-f",
            "-o",
            "ControlMaster=auto",
            "-S",
            "/tmp/control.sock",
            "-o",
            (
                "ProxyCommand="
                "/usr/bin/ssh -i /home/user/.ssh/proxy2 -W %h:%p -o StrictHostKeyChecking=no"
                " -o UserKnownHostsFile=/dev/null"
                " -o 'ProxyCommand=/usr/bin/ssh -i /home/user/.ssh/id_rsa -W %%h:%%p"
                " -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"
                " -p 10022 test1@proxy1'"
                " -p 20022 test2@proxy2"
            ),
            "ubuntu@my-server",
        ]

    @pytest.mark.usefixtures("ssh_client_info")
    def test_open_command_with_forwarding(self) -> None:
        tunnel = SSHTunnel(
            destination="ubuntu@my-server",
            identity=FilePath("/home/user/.ssh/id_rsa"),
            control_sock_path="/tmp/control.sock",
            options={},
            forwarded_sockets=[
                SocketPair(local=UnixSocket("/tmp/80"), remote=IPSocket("localhost", 80)),
                SocketPair(local=IPSocket("127.0.0.1", 8000), remote=IPSocket("::1", 80)),
            ],
            reverse_forwarded_sockets=[
                SocketPair(local=UnixSocket("/tmp/local"), remote=UnixSocket("/tmp/remote")),
                SocketPair(local=IPSocket("test.local", 80), remote=IPSocket("localhost", 8000)),
            ],
        )
        assert " ".join(tunnel.open_command()) == (
            "/usr/bin/ssh"
            " -F none"
            " -i /home/user/.ssh/id_rsa"
            f" -E {tunnel.temp_dir.name}/tunnel.log"
            " -N -f"
            " -o ControlMaster=auto"
            " -S /tmp/control.sock"
            " -L /tmp/80:localhost:80"
            " -L 127.0.0.1:8000:[::1]:80"
            " -R /tmp/remote:/tmp/local"
            " -R localhost:8000:test.local:80"
            " ubuntu@my-server"
        )

    def test_check_command(self, sample_tunnel_with_all_params: SSHTunnel) -> None:
        command = sample_tunnel_with_all_params.check_command()
        assert command == [
            "/usr/bin/ssh",
            "-S",
            "/tmp/control.sock",
            "-O",
            "check",
            "ubuntu@my-server",
        ]

    def test_close_command(self, sample_tunnel_with_all_params: SSHTunnel) -> None:
        command = sample_tunnel_with_all_params.close_command()
        assert command == [
            "/usr/bin/ssh",
            "-S",
            "/tmp/control.sock",
            "-O",
            "exit",
            "ubuntu@my-server",
        ]

    def test_exec_command(self, sample_tunnel_with_all_params: SSHTunnel) -> None:
        command = sample_tunnel_with_all_params.exec_command()
        assert command == ["/usr/bin/ssh", "-S", "/tmp/control.sock", "ubuntu@my-server"]


def test_ports_to_forwarded_sockets() -> None:
    assert ports_to_forwarded_sockets({80: 8000, 22: 2200}, bind_local="::1") == [
        SocketPair(local=IPSocket("::1", 8000), remote=IPSocket("localhost", 80)),
        SocketPair(local=IPSocket("::1", 2200), remote=IPSocket("localhost", 22)),
    ]
