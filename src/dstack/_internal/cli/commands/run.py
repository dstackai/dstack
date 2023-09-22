import argparse
from pathlib import Path

import requests

from dstack._internal.cli.commands import APIBaseCommand
from dstack._internal.core.errors import CLIError, ConfigurationError
from dstack._internal.core.services.configs import ConfigManager
from dstack._internal.core.services.configurator import load_run_spec
from dstack._internal.core.services.ssh.attach import SSHAttach
from dstack._internal.core.services.ssh.ports import PortsLock


class RunCommand(APIBaseCommand):
    NAME = "run"
    DESCRIPTION = "Run .dstack.yml configuration"

    def _command(self, args: argparse.Namespace):
        super()._command(args)
        try:
            run_spec = load_run_spec(
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

        # run_plan = self.api_client.runs.get_plan(self.project_name, run_spec)
        # TODO show plan

        ports_lock = PortsLock({10999: 0}).acquire()

        run = self.api_client.runs.submit(
            self.project_name, run_spec
        )  # TODO reliably handle interrupts
        stop_at_exit = True
        try:
            if args.detach:
                stop_at_exit = False
                return
            # TODO wait till running

            job = run.jobs[0].job_submissions[0]
            id_rsa_path = ConfigManager().get_repo_config(Path.cwd()).ssh_key_path
            with SSHAttach(
                job.job_provisioning_data.hostname, ports_lock, id_rsa_path, run.run_spec.run_name
            ) as attach:
                print(attach.ports)
                # TODO stream logs
        finally:
            if stop_at_exit:
                self.api_client.runs.stop(self.project_name, run.run_spec.run_name)

    def _register(self):
        super()._register()
        # TODO custom help action
        # self._parser.add_argument("-h", "--help", nargs="?", choices=("task", "dev-environment", "service"))
        self._parser.add_argument("working_dir")
        self._parser.add_argument("-f", "--file", type=Path, dest="configuration_file")
        self._parser.add_argument("--profile")  # TODO env var default
        self._parser.add_argument("--detach", action="store_true")
