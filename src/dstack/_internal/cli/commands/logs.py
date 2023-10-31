import argparse
import sys
from pathlib import Path

from dstack._internal.cli.commands import APIBaseCommand
from dstack._internal.core.errors import CLIError
from dstack._internal.core.services.ssh.ports import PortUsedError


class LogsCommand(APIBaseCommand):
    NAME = "logs"
    DESCRIPTION = "Show run logs"

    def _register(self):
        super()._register()
        self._parser.add_argument("-d", "--diagnose", action="store_true")
        self._parser.add_argument(
            "-a",
            "--attach",
            action="store_true",
            help="Set up an SSH tunnel, and print logs as they follow.",
        )
        self._parser.add_argument(
            "--ssh-identity",
            metavar="SSH_PRIVATE_KEY",
            help="A path to the private SSH key file for SSH tunneling",
            type=Path,
            dest="ssh_identity_file",
        )
        self._parser.add_argument("run_name")

    def _command(self, args: argparse.Namespace):
        super()._command(args)
        run = self.api.runs.get(args.run_name)
        if run is None:
            raise CLIError(f"Run {args.run_name} not found")
        if not args.diagnose and args.attach:
            if run.status.is_finished():
                raise CLIError(f"Run {args.run_name} is finished")
            else:
                run.attach(args.ssh_identity_file)
        logs = run.logs(diagnose=args.diagnose)
        try:
            for log in logs:
                sys.stdout.buffer.write(log)
                sys.stdout.buffer.flush()
        except KeyboardInterrupt:
            pass
