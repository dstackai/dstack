from typing import List, Optional

from dstack._internal.core.models.configurations import ConfigurationType, PortMapping
from dstack._internal.core.models.profiles import ProfileRetryPolicy, SpotPolicy
from dstack._internal.core.models.runs import RetryPolicy
from dstack._internal.server.services.jobs.configurators.base import JobConfigurator

DEFAULT_MAX_DURATION_SECONDS = 72 * 3600


class TaskJobConfigurator(JobConfigurator):
    TYPE: ConfigurationType = ConfigurationType.TASK

    def _shell_commands(self) -> List[str]:
        return self.run_spec.configuration.commands

    def _default_max_duration(self) -> Optional[int]:
        return DEFAULT_MAX_DURATION_SECONDS

    def _retry_policy(self) -> RetryPolicy:
        # convert ProfileRetryPolicy to RetryPolicy
        return RetryPolicy.parse_obj(self.run_spec.profile.retry_policy or ProfileRetryPolicy())

    def _spot_policy(self) -> SpotPolicy:
        return self.run_spec.profile.spot_policy or SpotPolicy.AUTO

    def _ports(self) -> List[PortMapping]:
        return self.run_spec.configuration.ports
