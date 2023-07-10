from typing import List, Optional

import dstack._internal.core.job as job
from dstack._internal.configurators import JobConfigurator
from dstack._internal.configurators.extensions.shell import require
from dstack._internal.configurators.extensions.ssh import SSHd
from dstack._internal.core.configuration import DevEnvironmentConfiguration
from dstack._internal.core.profile import Profile
from dstack._internal.core.repo import Repo
from dstack._internal.providers.extensions import VSCodeDesktopServer
from dstack._internal.providers.ports import get_map_to_port

require_sshd = require(["sshd"])
install_ipykernel = (
    f'pip install -q --no-cache-dir ipykernel || echo "no pip, ipykernel was not installed"'
)
vscode_extensions = ["ms-python.python", "ms-toolsai.jupyter"]


class DevEnvironmentConfigurator(JobConfigurator):
    conf: DevEnvironmentConfiguration

    # todo handle NoVSCodeVersionError
    def __init__(
        self,
        working_dir: str,
        configuration_path: str,
        configuration: DevEnvironmentConfiguration,
        profile: Profile,
    ):
        super().__init__(working_dir, configuration_path, configuration, profile)
        self.sshd: Optional[SSHd] = None

    def get_jobs(
        self, repo: Repo, run_name: str, repo_code_filename: str, ssh_key_pub: str
    ) -> List[job.Job]:
        self.sshd = SSHd(ssh_key_pub)
        self.sshd.map_to_port = get_map_to_port(self.ports(), self.sshd.port)
        return super().get_jobs(repo, run_name, repo_code_filename, ssh_key_pub)

    def commands(self) -> List[str]:
        commands = []
        if self.conf.image:
            require_sshd(commands)
            self.sshd.set_permissions(commands)
        self.sshd.start(commands)
        VSCodeDesktopServer.patch_commands(commands, vscode_extensions=vscode_extensions)
        commands.append(install_ipykernel)
        commands.extend(self.conf.init)
        commands.extend(
            [
                "echo ''",
                f"echo To open in VS Code Desktop, use one of these links:",
                f"echo ''",
                f"echo '  vscode://vscode-remote/ssh-remote+{self.run_name}/workflow'",
                "echo ''",
                f"echo 'To connect via SSH, use: `ssh {self.run_name}`'",
                "echo ''",
                "echo -n 'To exit, press Ctrl+C.'",
                "cat",  # idle
            ]
        )
        return commands

    def optional_build_commands(self) -> List[str]:
        commands = []
        if self.conf.image:
            require_sshd(commands)
        VSCodeDesktopServer.patch_setup(commands, vscode_extensions=vscode_extensions)
        commands.append(install_ipykernel)
        return commands

    def artifact_specs(self) -> List[job.ArtifactSpec]:
        return []  # not available

    def dep_specs(self) -> List[job.DepSpec]:
        return []  # not available

    def spot_policy(self) -> job.SpotPolicy:
        return self.profile.spot_policy or job.SpotPolicy.ONDEMAND

    def app_specs(self) -> List[job.AppSpec]:
        specs = super().app_specs()
        self.sshd.add_app(specs)
        return specs
