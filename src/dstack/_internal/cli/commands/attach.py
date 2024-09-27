import argparse
import sys
import time
from pathlib import Path
from typing import Optional

from dstack._internal.cli.commands import APIBaseCommand
from dstack._internal.cli.services.args import port_mapping
from dstack._internal.cli.utils.common import console
from dstack._internal.core.errors import CLIError
from dstack._internal.utils.common import get_or_error
from dstack.api._public.runs import Run


class AttachCommand(APIBaseCommand):
    NAME = "attach"
    DESCRIPTION = "Attach to the run"

    def _register(self):
        super()._register()
        self._parser.add_argument(
            "--ssh-identity",
            metavar="SSH_PRIVATE_KEY",
            help="The private SSH key path for SSH tunneling",
            type=Path,
            dest="ssh_identity_file",
        )
        self._parser.add_argument(
            "--logs",
            action="store_true",
            help="Print run logs as they follow",
        )
        self._parser.add_argument(
            "--host",
            help="Local address to bind. Defaults to [code]localhost[/].",
            metavar="HOST",
        )
        self._parser.add_argument(
            "-p",
            "--port",
            type=port_mapping,
            action="append",
            help="Port mapping overrides",
            dest="ports",
            metavar="MAPPING",
        )
        self._parser.add_argument(
            "--replica",
            help="The relica number. Defaults to 0.",
            type=int,
            default=0,
        )
        self._parser.add_argument(
            "--job",
            help="The job number inside the replica. Defaults to 0.",
            type=int,
            default=0,
        )
        self._parser.add_argument("run_name")

    def _command(self, args: argparse.Namespace):
        super()._command(args)
        run = self.api.runs.get(args.run_name)
        if run is None:
            raise CLIError(f"Run {args.run_name} not found")
        try:
            attached = run.attach(
                ssh_identity_file=args.ssh_identity_file,
                bind_address=args.host,
                ports_overrides=args.ports,
                replica_num=args.replica,
                job_num=args.job,
            )
            if not attached:
                raise CLIError(f"Failed to attach to run {args.run_name}")
            _print_attached_message(
                run=run,
                bind_address=args.host,
                replica_num=args.replica,
                job_num=args.job,
            )
            if args.logs:
                logs = run.logs(
                    replica_num=args.replica,
                    job_num=args.job,
                )
                try:
                    for log in logs:
                        sys.stdout.buffer.write(log)
                        sys.stdout.buffer.flush()
                except KeyboardInterrupt:
                    pass
            else:
                try:
                    while True:
                        time.sleep(10)
                except KeyboardInterrupt:
                    pass
        finally:
            run.detach()


_IGNORED_PORTS = [10999]


def _print_attached_message(
    run: Run,
    bind_address: Optional[str],
    replica_num: int,
    job_num: int,
):
    if bind_address is None:
        bind_address = "localhost"

    output = f"Attached to run [code]{run.name}[/] (replica={replica_num} job={job_num})\n"
    job = get_or_error(run._find_job(replica_num=replica_num, job_num=job_num))
    name = run.name
    if replica_num != 0 or job_num != 0:
        name = job.job_spec.job_name
    ports = get_or_error(run.ports)
    ports = {k: v for k, v in ports.items() if k not in _IGNORED_PORTS}
    if len(ports) > 0:
        output += "Forwarded ports (local -> remote):\n"
        for remote_port, local_port in ports.items():
            output += f"  - {bind_address}:{local_port} -> {remote_port}\n"
    output += f"To connect to the run via SSH, use `ssh {name}`.\n"
    output += "Press Ctrl+C to detach..."
    console.print(output)
