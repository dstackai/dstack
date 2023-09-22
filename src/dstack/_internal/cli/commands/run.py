import argparse
import tempfile
from pathlib import Path

import requests

from dstack._internal.cli.commands import APIBaseCommand
from dstack._internal.core.errors import CLIError, ConfigurationError
from dstack._internal.core.models.runs import JobStatus
from dstack._internal.core.services.configs import ConfigManager
from dstack._internal.core.services.configurator import load_run_spec
from dstack._internal.core.services.ssh.attach import SSHAttach
from dstack._internal.core.services.ssh.ports import PortsLock
from dstack.api.server.utils import poll_run


class RunCommand(APIBaseCommand):
    NAME = "run"
    DESCRIPTION = "Run .dstack.yml configuration"

    def _command(self, args: argparse.Namespace):
        super()._command(args)
        try:
            repo, run_spec = load_run_spec(
                Path().cwd(), args.working_dir, args.configuration_file, args.profile
            )
            self.api_client.repos.get(self.project_name, run_spec.repo_id, include_creds=False)
        except ConfigurationError as e:
            raise CLIError(f"Invalid configuration\n{e}")
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                raise CLIError(
                    f"Repository is not initialized in the project {self.project_name}. Call `dstack init` first"
                )
            raise

        ports_lock = None if args.detach else PortsLock({10999: 0}).acquire()
        # run_plan = self.api_client.runs.get_plan(self.project_name, run_spec)
        # TODO show plan

        with tempfile.TemporaryFile("w+b") as fp:
            run_spec.repo_code_hash = repo.write_code_file(fp)
            fp.seek(0)
            self.api_client.repos.upload_code(
                self.project_name, repo.repo_id, run_spec.repo_code_hash, fp
            )

        run = self.api_client.runs.submit(
            self.project_name, run_spec
        )  # TODO reliably handle interrupts
        run_name = run.run_spec.run_name
        print(run_name)

        if args.detach:
            print("Detaching...")
            return
        stop_at_exit = True
        try:
            for run in poll_run(self.api_client, self.project_name, run_name):
                print(run.status)  # TODO spinner with status
                if run.status not in (
                    JobStatus.SUBMITTED,
                    JobStatus.PENDING,
                    JobStatus.PROVISIONING,
                ):
                    break
            if run.status.is_finished() and run.status != JobStatus.DONE:
                stop_at_exit = False
                return

            print("Connecting...")
            hostname = run.jobs[0].job_submissions[0].job_provisioning_data.hostname
            id_rsa_path = ConfigManager().get_repo_config(Path.cwd()).ssh_key_path
            with SSHAttach(hostname, ports_lock, id_rsa_path, run_name) as attach:
                print(attach.ports)
                input("Press Enter to detach...")
                # TODO stream logs
        except KeyboardInterrupt:
            print("Interrupted")  # TODO ask to stop or just detach
        finally:
            if stop_at_exit:
                print("Stopping...")
                self.api_client.runs.stop(self.project_name, [run_name], abort=False)

    def _register(self):
        super()._register()
        # TODO custom help action
        # self._parser.add_argument("-h", "--help", nargs="?", choices=("task", "dev-environment", "service"))
        self._parser.add_argument("working_dir")
        self._parser.add_argument("-f", "--file", type=Path, dest="configuration_file")
        self._parser.add_argument("--profile")  # TODO env var default
        self._parser.add_argument("--detach", action="store_true")
