from typing import List, Optional

from dstack._internal.core.errors import ServerClientError
from dstack._internal.core.models.configurations import PortMapping, RunConfigurationType
from dstack._internal.core.models.profiles import SpotPolicy
from dstack._internal.core.models.runs import RunSpec
from dstack._internal.server.services.jobs.configurators.base import JobConfigurator
from dstack._internal.server.services.jobs.configurators.extensions.cursor import CursorDesktop
from dstack._internal.server.services.jobs.configurators.extensions.vscode import VSCodeDesktop

INSTALL_IPYKERNEL = (
    "(echo pip install ipykernel... && pip install -q --no-cache-dir ipykernel 2> /dev/null) || "
    'echo "no pip, ipykernel was not installed"'
)


class DevEnvironmentJobConfigurator(JobConfigurator):
    TYPE: RunConfigurationType = RunConfigurationType.DEV_ENVIRONMENT

    def __init__(self, run_spec: RunSpec):
        if run_spec.configuration.ide == "vscode":
            __class = VSCodeDesktop
        elif run_spec.configuration.ide == "cursor":
            __class = CursorDesktop
        else:
            raise ServerClientError(f"Unsupported IDE: {run_spec.configuration.ide}")
        self.ide = __class(
            run_name=run_spec.run_name,
            version=run_spec.configuration.version,
            extensions=["ms-python.python", "ms-toolsai.jupyter"],
        )
        super().__init__(run_spec)

    def _shell_commands(self) -> List[str]:
        commands = self.ide.get_install_commands()
        commands.append(INSTALL_IPYKERNEL)
        commands += self.run_spec.configuration.setup
        commands.append("echo ''")
        commands += self.run_spec.configuration.init
        commands += self.ide.get_print_readme_commands()
        commands += [
            f"echo 'To connect via SSH, use: `ssh {self.run_spec.run_name}`'",
            "echo ''",
            "echo -n 'To exit, press Ctrl+C.'",
        ]
        commands += ["tail -f /dev/null"]  # idle
        return commands

    def _default_single_branch(self) -> bool:
        return False

    def _default_max_duration(self) -> Optional[int]:
        return None

    def _spot_policy(self) -> SpotPolicy:
        return self.run_spec.merged_profile.spot_policy or SpotPolicy.ONDEMAND

    def _ports(self) -> List[PortMapping]:
        return self.run_spec.configuration.ports
