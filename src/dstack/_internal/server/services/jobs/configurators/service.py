from typing import List, Optional

from dstack._internal.core.models.configurations import PortMapping, RunConfigurationType
from dstack._internal.core.models.profiles import SpotPolicy
from dstack._internal.server.services.jobs.configurators.base import JobConfigurator


class ServiceJobConfigurator(JobConfigurator):
    TYPE: RunConfigurationType = RunConfigurationType.SERVICE

    def _shell_commands(self) -> List[str]:
        return self.run_spec.configuration.commands

    def _default_max_duration(self) -> Optional[int]:
        return None

    def _spot_policy(self) -> SpotPolicy:
        return self.run_spec.merged_profile.spot_policy or SpotPolicy.AUTO

    def _ports(self) -> List[PortMapping]:
        return []

    def _working_dir(self) -> Optional[str]:
        return None if not self._shell_commands() else super()._working_dir()
