import argparse
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from dstack._internal.cli.commands.connect import (
    ConnectCommand,
    launch_direct_connection,
    sshproxy_endpoint,
)
from dstack._internal.core.errors import CLIError
from dstack.api import RunDirectConnection


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers()
    ConnectCommand.register(subparsers)
    return parser


def _invoke(args: list[str], run: Mock):
    client = Mock()
    client.runs.get.return_value = run
    parsed_args = _parser().parse_args(["connect", "--project", "main", *args])
    parsed_args.extra_args = []
    with patch("dstack._internal.cli.commands.Client.from_config", return_value=client):
        parsed_args.func(parsed_args)
    return client


def _connection(
    *,
    ide: str | None = "zed",
    ide_name: str | None = "Zed",
    ide_command: tuple[str, ...] | None = (
        "zed",
        "ssh://upstream@dstack-direct-safealias/workspace",
    ),
    ssh_command: tuple[str, ...] = ("ssh", "upstream@dstack-direct-safealias"),
) -> RunDirectConnection:
    return RunDirectConnection(
        run_name="dev-run",
        replica_num=0,
        job_num=0,
        upstream_id="upstream",
        sshproxy_hostname="sshproxy.example.com",
        sshproxy_port=22,
        ssh_alias="dstack-direct-safealias",
        ssh_command=ssh_command,
        ide=ide,
        ide_name=ide_name,
        ide_command=ide_command,
    )


class TestConnectCommand:
    def test_launches_ssh_with_an_argument_vector(self, monkeypatch: pytest.MonkeyPatch) -> None:
        run = Mock()
        run.get_direct_connection.return_value = _connection()
        subprocess_run = Mock(return_value=SimpleNamespace(returncode=0))
        monkeypatch.setattr(
            "dstack._internal.cli.commands.connect.find_ssh_client",
            lambda: "/usr/bin/ssh",
        )
        monkeypatch.setattr(
            "dstack._internal.cli.commands.connect.subprocess.run",
            subprocess_run,
        )

        client = _invoke(
            [
                "--ssh",
                "--replica",
                "2",
                "--job",
                "1",
                "--expect-sshproxy",
                "sshproxy.example.com:2222",
                "dev-run",
            ],
            run,
        )

        client.runs.get.assert_called_once_with("dev-run")
        run.get_direct_connection.assert_called_once_with(
            replica_num=2,
            job_num=1,
            expected_sshproxy_hostname="sshproxy.example.com",
            expected_sshproxy_port=2222,
        )
        subprocess_run.assert_called_once_with(
            ["/usr/bin/ssh", "upstream@dstack-direct-safealias"],
            check=False,
        )

    @pytest.mark.parametrize(
        ("flag", "ide", "ide_name", "ide_command", "expected_command"),
        [
            (
                "--vscode",
                "vscode",
                "VS Code",
                (
                    "code",
                    "--folder-uri",
                    "vscode-remote://ssh-remote+upstream@safealias/workspace",
                ),
                [
                    "/usr/local/bin/code",
                    "--folder-uri",
                    "vscode-remote://ssh-remote+upstream@safealias/workspace",
                ],
            ),
            (
                "--cursor",
                "cursor",
                "Cursor",
                (
                    "cursor",
                    "--folder-uri",
                    "vscode-remote://ssh-remote+upstream@safealias/workspace",
                ),
                [
                    "/usr/local/bin/cursor",
                    "--folder-uri",
                    "vscode-remote://ssh-remote+upstream@safealias/workspace",
                ],
            ),
            (
                "--windsurf",
                "windsurf",
                "Windsurf",
                (
                    "windsurf",
                    "--folder-uri",
                    "vscode-remote://ssh-remote+upstream@safealias/workspace",
                ),
                [
                    "/usr/local/bin/windsurf",
                    "--folder-uri",
                    "vscode-remote://ssh-remote+upstream@safealias/workspace",
                ],
            ),
            (
                "--zed",
                "zed",
                "Zed",
                ("zed", "ssh://upstream@safealias/workspace"),
                ["/usr/local/bin/zed", "ssh://upstream@safealias/workspace"],
            ),
        ],
    )
    def test_launches_an_explicit_ide_with_an_argument_vector(
        self,
        flag: str,
        ide: str,
        ide_name: str,
        ide_command: tuple[str, ...],
        expected_command: list[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        run = Mock()
        run.get_direct_connection.return_value = _connection(
            ide=ide,
            ide_name=ide_name,
            ide_command=ide_command,
        )
        subprocess_run = Mock(return_value=SimpleNamespace(returncode=0))
        monkeypatch.setattr(
            "dstack._internal.cli.commands.connect.shutil.which",
            lambda executable: f"/usr/local/bin/{executable}",
        )
        monkeypatch.setattr(
            "dstack._internal.cli.commands.connect.subprocess.run",
            subprocess_run,
        )

        _invoke([flag, "dev-run"], run)

        subprocess_run.assert_called_once_with(expected_command, check=False)

    def test_launches_the_configured_ide(self, monkeypatch: pytest.MonkeyPatch) -> None:
        run = Mock()
        run.get_direct_connection.return_value = _connection(
            ide="cursor",
            ide_name="Cursor",
            ide_command=(
                "cursor",
                "--folder-uri",
                "vscode-remote://ssh-remote+upstream@safealias/workspace",
            ),
        )
        subprocess_run = Mock(return_value=SimpleNamespace(returncode=0))
        monkeypatch.setattr(
            "dstack._internal.cli.commands.connect.shutil.which",
            lambda executable: f"/usr/local/bin/{executable}",
        )
        monkeypatch.setattr(
            "dstack._internal.cli.commands.connect.subprocess.run",
            subprocess_run,
        )

        _invoke(["--ide", "dev-run"], run)

        subprocess_run.assert_called_once_with(
            [
                "/usr/local/bin/cursor",
                "--folder-uri",
                "vscode-remote://ssh-remote+upstream@safealias/workspace",
            ],
            check=False,
        )

    def test_rejects_an_explicit_ide_that_is_not_configured(self) -> None:
        run = Mock()
        run.get_direct_connection.return_value = _connection(
            ide=None,
            ide_name=None,
            ide_command=None,
        )

        with pytest.raises(CLIError, match="not configured for Zed"):
            _invoke(["--zed", "dev-run"], run)

    def test_rejects_configured_ide_mode_for_an_ssh_only_run(self) -> None:
        run = Mock()
        run.get_direct_connection.return_value = _connection(
            ide=None,
            ide_name=None,
            ide_command=None,
        )

        with pytest.raises(CLIError, match="not configured with an IDE"):
            _invoke(["--ide", "dev-run"], run)

    def test_uses_zeditor_when_zed_binary_name_is_unavailable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        run = Mock()
        run.get_direct_connection.return_value = _connection(
            ide_command=("zed", "ssh://upstream@safealias/workspace"),
        )
        subprocess_run = Mock(return_value=SimpleNamespace(returncode=0))
        monkeypatch.setattr(
            "dstack._internal.cli.commands.connect.shutil.which",
            lambda executable: "/usr/bin/zeditor" if executable == "zeditor" else None,
        )
        monkeypatch.setattr(
            "dstack._internal.cli.commands.connect.subprocess.run",
            subprocess_run,
        )

        _invoke(["--zed", "dev-run"], run)

        subprocess_run.assert_called_once_with(
            ["/usr/bin/zeditor", "ssh://upstream@safealias/workspace"],
            check=False,
        )

    def test_rejects_an_explicit_ide_that_does_not_match_the_configuration(self) -> None:
        run = Mock()
        run.get_direct_connection.return_value = _connection()

        with pytest.raises(CLIError, match="configured for Zed, not Cursor"):
            _invoke(["--cursor", "dev-run"], run)

    def test_rejects_a_missing_run(self) -> None:
        with pytest.raises(CLIError, match="Run missing not found"):
            _invoke(["missing"], None)

    def test_rejects_an_invalid_ssh_command(self) -> None:
        connection = _connection(ssh_command=("other", "unsafe"))

        with pytest.raises(CLIError, match="direct SSH command is invalid"):
            launch_direct_connection(connection)

    def test_rejects_an_invalid_ide_command(self) -> None:
        connection = _connection(ide_command=("other", "unsafe"))

        with pytest.raises(CLIError, match="direct IDE command is invalid"):
            launch_direct_connection(connection, mode="zed")

    def test_rejects_nonzero_client_exit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        run = Mock()
        run.get_direct_connection.return_value = _connection(
            ide=None,
            ide_name=None,
            ide_command=None,
        )
        monkeypatch.setattr(
            "dstack._internal.cli.commands.connect.find_ssh_client",
            lambda: "/usr/bin/ssh",
        )
        monkeypatch.setattr(
            "dstack._internal.cli.commands.connect.subprocess.run",
            lambda *_args, **_kwargs: SimpleNamespace(returncode=255),
        )

        with pytest.raises(CLIError, match="status 255"):
            _invoke(["dev-run"], run)

    def test_help_uses_standard_project_and_run_shape(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(SystemExit) as exc_info:
            _parser().parse_args(["connect", "--help"])

        assert exc_info.value.code == 0
        output = capsys.readouterr().out
        assert "--project NAME" in output
        for option in ("--ssh", "--ide", "--vscode", "--cursor", "--windsurf", "--zed"):
            assert option in output
        assert "--expect-sshproxy HOST[:PORT]" in output
        assert "run_name" in output


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("sshproxy.example.com", ("sshproxy.example.com", 22)),
        ("sshproxy.example.com:2222", ("sshproxy.example.com", 2222)),
        ("[2001:db8::1]:2222", ("2001:db8::1", 2222)),
    ],
)
def test_sshproxy_endpoint(value: str, expected: tuple[str, int]) -> None:
    assert sshproxy_endpoint(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "user@host",
        "host/path",
        "host:0",
        "host:",
        "host:70000",
        "host\nother",
        "[fe80::1%h]:22",
    ],
)
def test_sshproxy_endpoint_rejects_invalid_value(value: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        sshproxy_endpoint(value)
