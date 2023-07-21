from typing import List, Optional

import dstack._internal.core.job as job
from dstack._internal.configurators import JobConfigurator
from dstack._internal.configurators.extensions import IDEExtension
from dstack._internal.configurators.extensions.ssh import SSHd
from dstack._internal.configurators.extensions.vscode import VSCodeDesktop
from dstack._internal.configurators.ports import get_map_to_port
from dstack._internal.core.configuration import DevEnvironmentConfiguration
from dstack._internal.core.repo import Repo

DEFAULT_MAX_DURATION_SECONDS = 6 * 3600

install_ipykernel = f'(pip install -q --no-cache-dir ipykernel 2> /dev/null) || echo "no pip, ipykernel was not installed"'


class DevEnvironmentConfigurator(JobConfigurator):
    conf: DevEnvironmentConfiguration
    sshd: Optional[SSHd]
    ide: Optional[IDEExtension]

    def get_jobs(
        self, repo: Repo, run_name: str, repo_code_filename: str, ssh_key_pub: str
    ) -> List[job.Job]:
        self.ide = VSCodeDesktop(
            extensions=["ms-python.python", "ms-toolsai.jupyter"], run_name=run_name
        )
        self.sshd = SSHd(ssh_key_pub)
        self.sshd.map_to_port = get_map_to_port(self.ports(), self.sshd.port)
        return super().get_jobs(repo, run_name, repo_code_filename, ssh_key_pub)

    def optional_build_commands(self) -> List[str]:
        return []

    def setup(self) -> List[str]:
        commands = []
        if self.conf.image:
            commands += self.sshd.get_required_commands()
        commands += self.sshd.get_setup_commands()
        commands += self.ide.get_install_if_not_found_commands()
        commands.append(install_ipykernel)
        return commands

    def commands(self) -> List[str]:
        commands = []
        commands += self.sshd.get_start_commands()
        commands += self.conf.init
        commands.append("echo ''")
        commands += self.ide.get_print_readme_commands()
        commands += [
            f"echo 'To connect via SSH, use: `ssh {self.run_name}`'",
            "echo ''",
            "echo -n 'To exit, press Ctrl+C.'",
            "cat",  # idle
        ]
        return commands

    def default_max_duration(self) -> int:
        return DEFAULT_MAX_DURATION_SECONDS

    def artifact_specs(self) -> List[job.ArtifactSpec]:
        return []  # not available

    def dep_specs(self) -> List[job.DepSpec]:
        return []  # not available

    def app_specs(self) -> List[job.AppSpec]:
        specs = super().app_specs()
        specs.append(self.sshd.get_app_spec())
        return specs

    def spot_policy(self) -> job.SpotPolicy:
        return self.profile.spot_policy or job.SpotPolicy.ONDEMAND
