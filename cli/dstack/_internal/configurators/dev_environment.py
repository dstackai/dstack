from typing import List

from dstack._internal.configurators import JobConfigurator
from dstack._internal.core import job as job
from dstack._internal.core.configuration import DevEnvironmentConfiguration
from dstack._internal.providers.extensions import OpenSSHExtension, VSCodeDesktopServer

vscode_extensions = ["ms-python.python", "ms-toolsai.jupyter"]
pip_packages = ["ipykernel"]


class DevEnvironmentConfigurator(JobConfigurator):
    conf: DevEnvironmentConfiguration

    # todo handle NoVSCodeVersionError

    def commands(self) -> List[str]:
        commands = []
        # todo magic script
        OpenSSHExtension.patch_commands(commands, ssh_key_pub=self.ssh_key_pub)
        VSCodeDesktopServer.patch_commands(commands, vscode_extensions=vscode_extensions)
        commands.append("pip install -q --no-cache-dir " + " ".join(pip_packages))
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
        VSCodeDesktopServer.patch_setup(commands, vscode_extensions=vscode_extensions)
        commands.append("pip install -q --no-cache-dir " + " ".join(pip_packages))
        return commands

    def artifact_specs(self) -> List[job.ArtifactSpec]:
        return []  # not available

    def dep_specs(self) -> List[job.DepSpec]:
        return []  # not available

    def spot_policy(self) -> job.SpotPolicy:
        return self.profile.spot_policy or job.SpotPolicy.ONDEMAND

    def app_specs(self) -> List[job.AppSpec]:
        specs = super().app_specs()
        OpenSSHExtension.patch_apps(specs)
        return specs
