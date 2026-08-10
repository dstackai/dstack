import argparse
import shutil
import subprocess
from typing import Literal
from urllib.parse import urlsplit

from dstack._internal.cli.commands import APIBaseCommand
from dstack._internal.cli.services.completion import RunNameCompleter
from dstack._internal.core.errors import CLIError
from dstack._internal.utils.ssh import find_ssh_client
from dstack.api import Client, RunDirectConnection

ConnectionMode = Literal["ssh", "ide", "vscode", "cursor", "windsurf", "zed"]

_IDE_EXECUTABLES = {
    "vscode": ("code",),
    "cursor": ("cursor",),
    "windsurf": ("windsurf",),
    "zed": ("zed", "zeditor"),
}

_IDE_NAMES = {
    "vscode": "VS Code",
    "cursor": "Cursor",
    "windsurf": "Windsurf",
    "zed": "Zed",
}


def sshproxy_endpoint(value: str) -> tuple[str, int]:
    """Parse HOST[:PORT], including bracketed IPv6, without resolving it."""
    if "%" in value or any(c.isspace() or c == "\0" for c in value):
        raise argparse.ArgumentTypeError("Invalid SSH proxy endpoint")
    parsed = urlsplit(f"ssh://{value}")
    if (
        parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path
        or parsed.query
        or parsed.fragment
    ):
        raise argparse.ArgumentTypeError("Expected SSH proxy endpoint in HOST[:PORT] format")
    try:
        parsed_port = parsed.port
    except ValueError as e:
        raise argparse.ArgumentTypeError("Invalid SSH proxy port") from e
    if parsed_port is None:
        if value.endswith(":"):
            raise argparse.ArgumentTypeError("Invalid SSH proxy port")
        port = 22
    else:
        port = parsed_port
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("Invalid SSH proxy port")
    return parsed.hostname, port


def resolve_direct_connection(
    api: Client,
    run_name: str,
    *,
    replica_num: int | None = None,
    job_num: int = 0,
    expected_sshproxy: tuple[str, int] | None = None,
) -> RunDirectConnection:
    """Resolve and validate a run's direct SSH-proxy connection."""
    run = api.runs.get(run_name)
    if run is None:
        raise CLIError(f"Run {run_name} not found")

    expected_hostname = None
    expected_port = None
    if expected_sshproxy is not None:
        expected_hostname, expected_port = expected_sshproxy
    return run.get_direct_connection(
        replica_num=replica_num,
        job_num=job_num,
        expected_sshproxy_hostname=expected_hostname,
        expected_sshproxy_port=expected_port,
    )


def launch_direct_connection(
    connection: RunDirectConnection,
    *,
    mode: ConnectionMode = "ssh",
) -> None:
    """Launch a validated direct connection without invoking a shell."""
    if mode == "ssh":
        command = list(connection.ssh_command)
        if not command or command[0] != "ssh":
            raise CLIError("The direct SSH command is invalid")
        ssh_client = find_ssh_client()
        if ssh_client is None:
            raise CLIError("SSH client not found")
        executable = str(ssh_client)
        client_name = "SSH"
    else:
        requested_ide = None if mode == "ide" else mode
        if requested_ide is not None and requested_ide not in _IDE_EXECUTABLES:
            raise CLIError(f"Unsupported IDE: {requested_ide}")
        if connection.ide is None or connection.ide_command is None:
            if requested_ide is None:
                raise CLIError("The dev environment is not configured with an IDE")
            raise CLIError(
                f"The dev environment is not configured for {_IDE_NAMES[requested_ide]}"
            )
        if requested_ide is not None and connection.ide != requested_ide:
            requested_name = _IDE_NAMES[requested_ide]
            configured_name = connection.ide_name or connection.ide
            raise CLIError(
                f"The dev environment is configured for {configured_name}, not {requested_name}"
            )

        executable_names = _IDE_EXECUTABLES.get(connection.ide)
        if executable_names is None:
            raise CLIError(f"Unsupported configured IDE: {connection.ide}")
        command = list(connection.ide_command)
        if not command or command[0] != executable_names[0]:
            raise CLIError("The direct IDE command is invalid")
        executable = next(
            (path for name in executable_names if (path := shutil.which(name)) is not None),
            None,
        )
        client_name = connection.ide_name or _IDE_NAMES[connection.ide]
        if executable is None:
            names = " or ".join(f"`{name}`" for name in executable_names)
            raise CLIError(
                f"{client_name} CLI not found. Install the {names} command and try again"
            )

    command[0] = executable
    result = subprocess.run(command, check=False)
    if result.returncode != 0:
        raise CLIError(f"{client_name} client exited with status {result.returncode}")


class ConnectCommand(APIBaseCommand):
    NAME = "connect"
    DESCRIPTION = "Connect directly to a running dev environment"

    def _register(self):
        super()._register()
        mode = self._parser.add_mutually_exclusive_group()
        mode.add_argument(
            "--ssh",
            action="store_const",
            const="ssh",
            dest="mode",
            help="Open an interactive SSH shell (default)",
        )
        mode.add_argument(
            "--ide",
            action="store_const",
            const="ide",
            dest="mode",
            help="Open the configured IDE",
        )
        mode.add_argument(
            "--vscode",
            action="store_const",
            const="vscode",
            dest="mode",
            help="Open the dev environment in VS Code",
        )
        mode.add_argument(
            "--cursor",
            action="store_const",
            const="cursor",
            dest="mode",
            help="Open the dev environment in Cursor",
        )
        mode.add_argument(
            "--windsurf",
            action="store_const",
            const="windsurf",
            dest="mode",
            help="Open the dev environment in Windsurf",
        )
        mode.add_argument(
            "--zed",
            action="store_const",
            const="zed",
            dest="mode",
            help="Open the dev environment in Zed",
        )
        self._parser.set_defaults(mode="ssh")
        self._parser.add_argument(
            "--replica",
            help="The replica number. Defaults to any running replica.",
            type=int,
        )
        self._parser.add_argument(
            "--job",
            help="The job number inside the replica. Defaults to 0.",
            type=int,
            default=0,
        )
        self._parser.add_argument(
            "--expect-sshproxy",
            metavar="HOST[:PORT]",
            type=sshproxy_endpoint,
            help="Fail unless the run uses this exact SSH proxy endpoint",
        )
        self._parser.add_argument("run_name").completer = RunNameCompleter()  # type: ignore[attr-defined]

    def _command(self, args: argparse.Namespace):
        super()._command(args)
        connection = resolve_direct_connection(
            self.api,
            args.run_name,
            replica_num=args.replica,
            job_num=args.job,
            expected_sshproxy=args.expect_sshproxy,
        )
        launch_direct_connection(connection, mode=args.mode)
