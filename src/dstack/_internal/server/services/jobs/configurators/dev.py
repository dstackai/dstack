from typing import Dict, List, Optional

from dstack._internal.core.errors import ServerClientError
from dstack._internal.core.models.configurations import PortMapping, RunConfigurationType
from dstack._internal.core.models.profiles import SpotPolicy
from dstack._internal.core.models.runs import RunSpec
from dstack._internal.server.services.ides import get_ide
from dstack._internal.server.services.jobs.configurators.base import JobConfigurator

INSTALL_IPYKERNEL = (
    "(echo 'pip install ipykernel...' && pip install -q --no-cache-dir ipykernel 2> /dev/null) || "
    "echo 'no pip, ipykernel was not installed'"
)


class DevEnvironmentJobConfigurator(JobConfigurator):
    TYPE: RunConfigurationType = RunConfigurationType.DEV_ENVIRONMENT

    ide_extensions = ["ms-python.python", "ms-toolsai.jupyter"]

    def __init__(
        self, run_spec: RunSpec, secrets: Dict[str, str], replica_group_name: Optional[str] = None
    ):
        assert run_spec.configuration.type == "dev-environment"

        if run_spec.configuration.ide is None:
            self.ide = None
        else:
            ide = get_ide(run_spec.configuration.ide)
            if ide is None:
                raise ServerClientError(f"Unsupported IDE: {run_spec.configuration.ide}")
            self.ide = ide
        super().__init__(run_spec=run_spec, secrets=secrets, replica_group_name=replica_group_name)

    def _shell_commands(self) -> List[str]:
        assert self.run_spec.configuration.type == "dev-environment"

        commands = []
        if self.ide is not None:
            commands += self.ide.get_install_commands(
                version=self.run_spec.configuration.version, extensions=self.ide_extensions
            )
        commands.append(INSTALL_IPYKERNEL)
        commands += self.run_spec.configuration.setup
        commands.append("echo")
        commands += self.run_spec.configuration.init
        if self.ide is not None:
            assert self.run_spec.run_name is not None
            commands += self.ide.get_print_readme_commands(self.run_spec.run_name)
        commands += [
            f"echo 'To connect via SSH, use: `ssh {self.run_spec.run_name}`'",
            "echo",
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
        assert self.run_spec.configuration.type == "dev-environment"
        return self.run_spec.configuration.ports
