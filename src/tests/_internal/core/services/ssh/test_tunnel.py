import asyncio
import signal
import subprocess
from pathlib import Path
from typing import NoReturn, Optional
from unittest.mock import AsyncMock, Mock

import pytest

from dstack._internal.compat import IS_WINDOWS
from dstack._internal.core.errors import SSHError
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

    @pytest.fixture
    def foreground_tunnel(self, ssh_client_info: SSHClientInfo) -> SSHTunnel:
        return SSHTunnel(
            destination="ubuntu@my-server",
            identity=FilePath("/home/user/.ssh/id_rsa"),
            background=False,
        )

    @pytest.fixture
    def kill_process_group(self, monkeypatch: pytest.MonkeyPatch) -> Mock:
        kill_process_group = Mock()
        monkeypatch.setattr(
            "dstack._internal.core.services.ssh.tunnel.os.killpg",
            kill_process_group,
            raising=False,
        )
        return kill_process_group

    @pytest.fixture
    def ssh_process(self, monkeypatch: pytest.MonkeyPatch, kill_process_group: Mock) -> Mock:
        process = Mock(spec=asyncio.subprocess.Process)
        process.pid = 12345
        process.returncode = None
        process.communicate.return_value = (b"", b"")
        monkeypatch.setattr(asyncio, "create_subprocess_exec", AsyncMock(return_value=process))
        return process

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
        assert " ".join(command) == (
            "/usr/bin/ssh -F none -o BatchMode=yes -S /tmp/control.sock -O check ubuntu@my-server"
        )

    def test_close_command(self, sample_tunnel_with_all_params: SSHTunnel) -> None:
        command = sample_tunnel_with_all_params.close_command()
        assert " ".join(command) == (
            "/usr/bin/ssh -F none -o BatchMode=yes -S /tmp/control.sock -O exit ubuntu@my-server"
        )

    def test_exec_command(self, sample_tunnel_with_all_params: SSHTunnel) -> None:
        command = sample_tunnel_with_all_params.exec_command()
        assert " ".join(command) == (
            "/usr/bin/ssh -F none -o BatchMode=yes -S /tmp/control.sock ubuntu@my-server"
        )

    def test_foreground_command_owns_process(self, foreground_tunnel: SSHTunnel) -> None:
        foreground_tunnel.options = {
            "ForkAfterAuthentication": "yes",
            "ControlPersist": "yes",
            "ControlMaster": "auto",
        }
        command = foreground_tunnel.open_command()

        assert "-f" not in command
        # OpenSSH honors the first value, so user/config options cannot detach the process.
        assert command.index("ForkAfterAuthentication=no") < command.index(
            "ForkAfterAuthentication=yes"
        )
        assert command.index("ControlPersist=no") < command.index("ControlPersist=yes")
        assert command.index("ControlMaster=yes") < command.index("ControlMaster=auto")

    def test_foreground_requires_async_open(self, foreground_tunnel: SSHTunnel) -> None:
        with pytest.raises(SSHError, match="require aopen"):
            foreground_tunnel.open()

    @pytest.mark.asyncio
    async def test_background_aopen_keeps_existing_behavior(
        self,
        sample_tunnel_with_all_params: SSHTunnel,
        ssh_process: Mock,
        kill_process_group: Mock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        create_process = AsyncMock(return_value=ssh_process)
        monkeypatch.setattr(asyncio, "create_subprocess_exec", create_process)
        ssh_process.returncode = 0

        await sample_tunnel_with_all_params.aopen()

        assert "-f" in create_process.call_args.args
        assert "start_new_session" not in create_process.call_args.kwargs
        ssh_process.communicate.assert_awaited_once_with()
        ssh_process.wait.assert_not_called()
        ssh_process.kill.assert_not_called()
        kill_process_group.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "is_windows",
        [True, pytest.param(False, marks=pytest.mark.skipif(IS_WINDOWS, reason="POSIX signals"))],
    )
    async def test_foreground_waits_for_readiness_then_process_exit(
        self,
        foreground_tunnel: SSHTunnel,
        ssh_process: Mock,
        kill_process_group: Mock,
        monkeypatch: pytest.MonkeyPatch,
        is_windows: bool,
    ) -> None:
        monkeypatch.setattr("dstack._internal.core.services.ssh.tunnel.IS_WINDOWS", is_windows)
        create_process = AsyncMock(return_value=ssh_process)
        monkeypatch.setattr(asyncio, "create_subprocess_exec", create_process)
        Path(foreground_tunnel.control_sock_path).touch()
        checking = asyncio.Event()
        ready = asyncio.Event()
        waiting_for_exit = asyncio.Event()
        exited = asyncio.Event()

        async def check():
            checking.set()
            await ready.wait()
            return True

        async def wait():
            waiting_for_exit.set()
            await exited.wait()
            return ssh_process.returncode

        check_mock = AsyncMock(side_effect=check)
        monkeypatch.setattr(foreground_tunnel, "acheck", check_mock)
        ssh_process.wait.side_effect = wait
        opening = asyncio.create_task(foreground_tunnel.aopen())
        await checking.wait()
        assert not opening.done()
        ready.set()
        await opening

        assert create_process.call_args.kwargs["start_new_session"] is not is_windows
        ssh_process.communicate.assert_not_called()
        ssh_process.wait.assert_not_called()
        waiting = asyncio.create_task(foreground_tunnel.wait_closed())
        await waiting_for_exit.wait()
        assert not waiting.done()
        ssh_process.returncode = 255
        exited.set()
        assert await waiting == 255
        check_mock.assert_awaited_once_with()

        # Keep the handle after exit: the process group can still contain proxy children.
        await foreground_tunnel.aclose()
        if is_windows:
            ssh_process.kill.assert_called_once_with()
            kill_process_group.assert_not_called()
        else:
            kill_process_group.assert_called_once_with(ssh_process.pid, signal.SIGKILL)
            ssh_process.kill.assert_not_called()
        assert ssh_process.wait.await_count == 2
        assert not Path(foreground_tunnel.control_sock_path).exists()
        await foreground_tunnel.aclose()
        assert ssh_process.wait.await_count == 2
        with pytest.raises(SSHError, match="No foreground SSH process"):
            await foreground_tunnel.wait_closed()

    @pytest.mark.asyncio
    async def test_foreground_checks_only_after_control_socket_exists(
        self,
        foreground_tunnel: SSHTunnel,
        ssh_process: Mock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        polling = asyncio.Event()
        create_socket = asyncio.Event()
        check = AsyncMock(return_value=True)
        monkeypatch.setattr(foreground_tunnel, "acheck", check)

        async def startup_poll(interval):
            assert interval == 0.1
            polling.set()
            await create_socket.wait()
            Path(foreground_tunnel.control_sock_path).touch()

        monkeypatch.setattr(asyncio, "sleep", startup_poll)
        opening = asyncio.create_task(foreground_tunnel.aopen())
        await polling.wait()
        check.assert_not_called()
        create_socket.set()
        await opening
        check.assert_awaited_once_with()

        with pytest.raises(SSHError, match="Close the previous foreground SSH process"):
            await foreground_tunnel.aopen()
        await foreground_tunnel.aclose()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("during_check", [False, True])
    async def test_foreground_early_exit_fails_startup_and_cleans_up(
        self,
        foreground_tunnel: SSHTunnel,
        ssh_process: Mock,
        kill_process_group: Mock,
        monkeypatch: pytest.MonkeyPatch,
        during_check: bool,
    ) -> None:
        Path(foreground_tunnel.control_sock_path).touch()

        async def check():
            ssh_process.returncode = 255
            return True

        check_mock = AsyncMock(side_effect=check)
        monkeypatch.setattr(foreground_tunnel, "acheck", check_mock)
        if not during_check:
            ssh_process.returncode = 255

        with pytest.raises(SSHError):
            await foreground_tunnel.aopen()

        assert check_mock.await_count == int(during_check)
        if IS_WINDOWS:
            ssh_process.kill.assert_called_once_with()
        else:
            kill_process_group.assert_called_once_with(ssh_process.pid, signal.SIGKILL)
        ssh_process.wait.assert_awaited_once_with()
        assert not Path(foreground_tunnel.control_sock_path).exists()
        with pytest.raises(SSHError, match="No foreground SSH process"):
            await foreground_tunnel.wait_closed()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("method", ["aopen", "acheck"])
    @pytest.mark.parametrize("already_exited", [False, True])
    @pytest.mark.parametrize(
        "is_windows",
        [True, pytest.param(False, marks=pytest.mark.skipif(IS_WINDOWS, reason="POSIX signals"))],
    )
    async def test_cancelled_command_kills_and_reaps_process(
        self,
        foreground_tunnel: SSHTunnel,
        ssh_process: Mock,
        kill_process_group: Mock,
        monkeypatch: pytest.MonkeyPatch,
        method: str,
        already_exited: bool,
        is_windows: bool,
    ) -> None:
        monkeypatch.setattr("dstack._internal.core.services.ssh.tunnel.IS_WINDOWS", is_windows)
        waiting = asyncio.Event()

        async def wait_for_process(*args):
            if ssh_process.returncode is None:
                waiting.set()
                await asyncio.Future()
            return ssh_process.returncode

        def kill(*args) -> None:
            ssh_process.returncode = 0 if already_exited else -9
            if already_exited:
                raise ProcessLookupError

        monkeypatch.setattr(
            foreground_tunnel, "_wait_until_ready", AsyncMock(side_effect=wait_for_process)
        )
        ssh_process.communicate.side_effect = wait_for_process
        ssh_process.wait.side_effect = wait_for_process
        ssh_process.kill.side_effect = kill
        kill_process_group.side_effect = kill
        task = asyncio.create_task(getattr(foreground_tunnel, method)())
        await waiting.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        if method == "aopen" and not is_windows:
            kill_process_group.assert_called_once_with(ssh_process.pid, signal.SIGKILL)
            ssh_process.kill.assert_not_called()
        else:
            ssh_process.kill.assert_called_once_with()
            kill_process_group.assert_not_called()
        ssh_process.wait.assert_awaited_once_with()
        assert task.cancelled()

    @pytest.mark.asyncio
    async def test_cancelled_foreground_readiness_cleans_check_and_master(
        self,
        foreground_tunnel: SSHTunnel,
        ssh_process: Mock,
        kill_process_group: Mock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        Path(foreground_tunnel.control_sock_path).touch()
        check_process = Mock(spec=asyncio.subprocess.Process)
        check_process.returncode = None
        waiting = asyncio.Event()

        async def wait():
            if check_process.returncode is None:
                waiting.set()
                await asyncio.Future()
            return check_process.returncode

        def kill():
            check_process.returncode = -9

        check_process.communicate.side_effect = wait
        check_process.kill.side_effect = kill
        create_process = AsyncMock(side_effect=[ssh_process, check_process])
        monkeypatch.setattr(asyncio, "create_subprocess_exec", create_process)
        opening = asyncio.create_task(foreground_tunnel.aopen())
        await waiting.wait()
        opening.cancel()
        with pytest.raises(asyncio.CancelledError):
            await opening

        check_process.kill.assert_called_once_with()
        check_process.communicate.assert_awaited_once_with()
        check_process.wait.assert_awaited_once_with()
        if IS_WINDOWS:
            ssh_process.kill.assert_called_once_with()
        else:
            kill_process_group.assert_called_once_with(ssh_process.pid, signal.SIGKILL)
        ssh_process.wait.assert_awaited_once_with()
        assert foreground_tunnel._process is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize("already_exited", [False, True])
    @pytest.mark.parametrize(
        "is_windows",
        [True, pytest.param(False, marks=pytest.mark.skipif(IS_WINDOWS, reason="POSIX signals"))],
    )
    async def test_timed_out_aopen_kills_and_reaps_process(
        self,
        foreground_tunnel: SSHTunnel,
        ssh_process: Mock,
        kill_process_group: Mock,
        monkeypatch: pytest.MonkeyPatch,
        already_exited: bool,
        is_windows: bool,
    ) -> None:
        # A zero timeout exercises wait_for's cleanup without waiting on real time.
        monkeypatch.setattr("dstack._internal.core.services.ssh.tunnel.SSH_TIMEOUT", 0)
        monkeypatch.setattr("dstack._internal.core.services.ssh.tunnel.IS_WINDOWS", is_windows)
        if already_exited:
            ssh_process.kill.side_effect = ProcessLookupError
            kill_process_group.side_effect = ProcessLookupError

        with pytest.raises(SSHError, match="in 0 seconds") as exc_info:
            await foreground_tunnel.aopen()

        if not is_windows:
            kill_process_group.assert_called_once_with(ssh_process.pid, signal.SIGKILL)
            ssh_process.kill.assert_not_called()
        else:
            ssh_process.kill.assert_called_once_with()
            kill_process_group.assert_not_called()
        ssh_process.wait.assert_awaited_once_with()
        assert isinstance(exc_info.value.__cause__, asyncio.TimeoutError)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "is_windows",
        [True, pytest.param(False, marks=pytest.mark.skipif(IS_WINDOWS, reason="POSIX signals"))],
    )
    async def test_cancelled_aopen_during_creation_kills_and_reaps_process(
        self,
        foreground_tunnel: SSHTunnel,
        ssh_process: Mock,
        kill_process_group: Mock,
        monkeypatch: pytest.MonkeyPatch,
        is_windows: bool,
    ) -> None:
        monkeypatch.setattr("dstack._internal.core.services.ssh.tunnel.IS_WINDOWS", is_windows)
        spawned = asyncio.Event()
        return_process = asyncio.Event()
        returned = asyncio.Event()

        async def create_process(*args, **kwargs):
            # Creation has spawned SSH but has not yet returned its handle to aopen().
            spawned.set()
            await return_process.wait()
            returned.set()
            return ssh_process

        monkeypatch.setattr(asyncio, "create_subprocess_exec", create_process)
        task = asyncio.create_task(foreground_tunnel.aopen())
        await spawned.wait()
        task.cancel("cancel while creating SSH")
        return_process.set()
        with pytest.raises(asyncio.CancelledError, match="cancel while creating SSH"):
            await task

        assert returned.is_set()
        if is_windows:
            ssh_process.kill.assert_called_once_with()
            kill_process_group.assert_not_called()
        else:
            kill_process_group.assert_called_once_with(ssh_process.pid, signal.SIGKILL)
            ssh_process.kill.assert_not_called()
        ssh_process.wait.assert_awaited_once_with()
        ssh_process.communicate.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("cancelled", [False, True])
    async def test_aopen_process_creation_failure_preserves_cancellation(
        self,
        foreground_tunnel: SSHTunnel,
        kill_process_group: Mock,
        monkeypatch: pytest.MonkeyPatch,
        cancelled: bool,
    ) -> None:
        creating = asyncio.Event()
        fail_creation = asyncio.Event()
        failure = OSError("SSH could not start")

        async def create_process(*args, **kwargs):
            creating.set()
            await fail_creation.wait()
            raise failure

        monkeypatch.setattr(asyncio, "create_subprocess_exec", create_process)
        task = asyncio.create_task(foreground_tunnel.aopen())
        await creating.wait()
        if cancelled:
            task.cancel("cancel while creating SSH")
        fail_creation.set()

        if cancelled:
            with pytest.raises(asyncio.CancelledError, match="cancel while creating SSH"):
                await task
        else:
            with pytest.raises(OSError) as exc_info:
                await task
            assert exc_info.value is failure
        kill_process_group.assert_not_called()

    @pytest.mark.asyncio
    async def test_cancelled_aclose_waits_for_cleanup(
        self,
        foreground_tunnel: SSHTunnel,
        ssh_process: Mock,
        kill_process_group: Mock,
    ) -> None:
        foreground_tunnel._process = ssh_process
        Path(foreground_tunnel.control_sock_path).touch()
        reaping = asyncio.Event()
        reaped = asyncio.Event()

        async def wait():
            reaping.set()
            await reaped.wait()
            return -9

        ssh_process.wait.side_effect = wait
        closing = asyncio.create_task(foreground_tunnel.aclose())
        await reaping.wait()
        closing.cancel("cancel during cleanup")
        reaped.set()
        with pytest.raises(asyncio.CancelledError, match="cancel during cleanup"):
            await closing

        ssh_process.wait.assert_awaited_once_with()
        assert foreground_tunnel._process is None
        assert not Path(foreground_tunnel.control_sock_path).exists()
        if IS_WINDOWS:
            ssh_process.kill.assert_called_once_with()
        else:
            kill_process_group.assert_called_once_with(ssh_process.pid, signal.SIGKILL)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("returncode", [0, 255])
    async def test_acheck_returns_process_status(
        self,
        sample_tunnel_with_all_params: SSHTunnel,
        ssh_process: Mock,
        returncode: int,
    ) -> None:
        ssh_process.returncode = returncode

        assert await sample_tunnel_with_all_params.acheck() is (returncode == 0)

        ssh_process.kill.assert_not_called()


class TestSSHTunnelControlTimeouts:
    @pytest.fixture
    def tunnel(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> SSHTunnel:
        monkeypatch.setattr(
            "dstack._internal.core.services.ssh.client._ssh_client_info",
            SSHClientInfo.from_raw_version("OpenSSH_9.7p1", Path("/usr/bin/ssh")),
        )
        control_sock_path = tmp_path / "control.sock"
        control_sock_path.touch()
        return SSHTunnel(
            destination="ubuntu@my-server",
            identity=FilePath("/home/user/.ssh/id_rsa"),
            control_sock_path=control_sock_path,
        )

    @pytest.fixture
    def hanging_process(self, monkeypatch: pytest.MonkeyPatch) -> "_HangingProcess":
        process = _HangingProcess()

        async def create_subprocess_exec(*args, **kwargs):
            return process

        monkeypatch.setattr(asyncio, "create_subprocess_exec", create_subprocess_exec)
        monkeypatch.setattr("dstack._internal.core.services.ssh.tunnel.SSH_TIMEOUT", 0)
        return process

    @pytest.fixture
    def timing_out_run(self, monkeypatch: pytest.MonkeyPatch) -> Mock:
        run = Mock(side_effect=subprocess.TimeoutExpired(cmd="ssh", timeout=0))
        monkeypatch.setattr(subprocess, "run", run)
        return run

    def test_check_returns_false_on_timeout(self, tunnel: SSHTunnel, timing_out_run: Mock) -> None:
        assert tunnel.check() is False
        assert timing_out_run.call_args.kwargs["stdin"] == subprocess.DEVNULL

    def test_close_does_not_raise_on_timeout(
        self, tunnel: SSHTunnel, timing_out_run: Mock
    ) -> None:
        tunnel.close()
        assert timing_out_run.call_args.kwargs["stdin"] == subprocess.DEVNULL

    @pytest.mark.asyncio
    async def test_acheck_kills_process_and_returns_false_on_timeout(
        self, tunnel: SSHTunnel, hanging_process: "_HangingProcess"
    ) -> None:
        assert await tunnel.acheck() is False
        assert hanging_process.killed

    @pytest.mark.asyncio
    async def test_aclose_kills_process_on_timeout(
        self, tunnel: SSHTunnel, hanging_process: "_HangingProcess"
    ) -> None:
        await tunnel.aclose()
        assert hanging_process.killed

    @pytest.mark.asyncio
    async def test_aexec_kills_process_and_raises_on_timeout(
        self, tunnel: SSHTunnel, hanging_process: "_HangingProcess"
    ) -> None:
        with pytest.raises(SSHError, match="did not complete"):
            await tunnel.aexec("true", timeout=0)
        assert hanging_process.killed

    @pytest.mark.asyncio
    @pytest.mark.parametrize("method", ["acheck", "aclose", "aexec"])
    @pytest.mark.parametrize("already_exited", [False, True])
    async def test_cancelled_control_command_kills_and_reaps_process(
        self,
        tunnel: SSHTunnel,
        monkeypatch: pytest.MonkeyPatch,
        method: str,
        already_exited: bool,
    ) -> None:
        process = Mock(spec=asyncio.subprocess.Process)
        communicating = asyncio.Event()

        async def communicate():
            communicating.set()
            await asyncio.Future()

        process.communicate.side_effect = communicate
        if already_exited:
            process.kill.side_effect = ProcessLookupError
        monkeypatch.setattr(asyncio, "create_subprocess_exec", AsyncMock(return_value=process))
        command = getattr(tunnel, method)(*(["true"] if method == "aexec" else []))
        task = asyncio.create_task(command)
        await communicating.wait()
        task.cancel("cancel control command")

        with pytest.raises(asyncio.CancelledError, match="cancel control command"):
            await task

        process.kill.assert_called_once_with()
        process.wait.assert_awaited_once_with()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("method", ["acheck", "aclose", "aexec"])
    async def test_timeout_preserves_behavior_when_process_has_already_exited(
        self,
        tunnel: SSHTunnel,
        hanging_process: "_HangingProcess",
        monkeypatch: pytest.MonkeyPatch,
        method: str,
    ) -> None:
        def kill():
            hanging_process.returncode = 0
            raise ProcessLookupError

        reaped = AsyncMock(wraps=hanging_process.wait)
        monkeypatch.setattr(hanging_process, "kill", kill)
        monkeypatch.setattr(hanging_process, "wait", reaped)
        if method == "aexec":
            with pytest.raises(SSHError, match="did not complete") as exc_info:
                await tunnel.aexec("true", timeout=0)
            assert isinstance(exc_info.value.__cause__, asyncio.TimeoutError)
        else:
            result = await getattr(tunnel, method)()
            assert result is (False if method == "acheck" else None)
        reaped.assert_awaited_once_with()


class _HangingProcess:
    def __init__(self) -> None:
        self.returncode: Optional[int] = None
        self.killed = False

    async def communicate(self) -> NoReturn:
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9

    async def wait(self) -> int:
        assert self.returncode is not None
        return self.returncode


def test_ports_to_forwarded_sockets() -> None:
    assert ports_to_forwarded_sockets({80: 8000, 22: 2200}, bind_local="::1") == [
        SocketPair(local=IPSocket("::1", 8000), remote=IPSocket("localhost", 80)),
        SocketPair(local=IPSocket("::1", 2200), remote=IPSocket("localhost", 22)),
    ]
