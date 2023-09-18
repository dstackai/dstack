from typing import List, Optional

from dstack._internal.core.models.configurations import ConfigurationType
from dstack._internal.core.models.profiles import SpotPolicy
from dstack._internal.core.models.runs import RetryPolicy, RunSpec
from dstack._internal.server.services.jobs.configurators.base import JobConfigurator
from dstack._internal.server.services.jobs.configurators.extensions.ssh import SSHd
from dstack._internal.server.services.jobs.configurators.extensions.vscode import VSCodeDesktop

DEFAULT_MAX_DURATION_SECONDS = 6 * 3600

INSTALL_IPYKERNEL = f'(pip install -q --no-cache-dir ipykernel 2> /dev/null) || echo "no pip, ipykernel was not installed"'


class DevEnvironmentJobConfigurator(JobConfigurator):
    TYPE: ConfigurationType = ConfigurationType.DEV_ENVIRONMENT

    def __init__(self, run_spec: RunSpec):
        self.ide = VSCodeDesktop(
            run_name=run_spec.run_name,
            version="1",  # TODO pass version
            extensions=["ms-python.python", "ms-toolsai.jupyter"],
        )
        self.sshd = SSHd(run_spec.ssh_key_pub)
        super().__init__(run_spec)

    def _commands(self) -> List[str]:
        commands = []
        commands += self.sshd.get_start_commands()
        commands += self.run_spec.configuration.init
        commands += ["cat"]  # idle
        return commands

    def _default_max_duration(self) -> Optional[int]:
        return DEFAULT_MAX_DURATION_SECONDS

    def _retry_policy(self) -> RetryPolicy:
        return RetryPolicy.parse_obj(self.run_spec.profile.retry_policy)

    def _setup(self) -> List[str]:
        commands = []
        if self.run_spec.configuration.image:
            commands += self.sshd.get_required_commands()
        commands += self.sshd.get_setup_commands()
        commands += self.ide.get_install_if_not_found_commands()
        commands.append(INSTALL_IPYKERNEL)
        commands += self.run_spec.configuration.setup
        commands.append("echo ''")
        commands += self.ide.get_print_readme_commands()
        commands += [
            f"echo 'To connect via SSH, use: `ssh {self.run_spec.run_name}`'",
            "echo ''",
            "echo -n 'To exit, press Ctrl+C.'",
        ]
        return commands

    def _spot_policy(self) -> SpotPolicy:
        return self.run_spec.profile.spot_policy or SpotPolicy.ONDEMAND
