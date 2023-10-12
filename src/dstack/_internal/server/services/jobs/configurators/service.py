from typing import List, Optional

from dstack._internal.core.models.configurations import ConfigurationType, PortMapping
from dstack._internal.core.models.profiles import SpotPolicy
from dstack._internal.core.models.runs import Gateway, RetryPolicy
from dstack._internal.server.services.jobs.configurators.base import JobConfigurator


class ServiceJobConfigurator(JobConfigurator):
    TYPE: ConfigurationType = ConfigurationType.SERVICE

    def _gateway(self) -> Optional[Gateway]:
        return Gateway(
            gateway_name=None,  # TODO configurable
            service_port=self.run_spec.configuration.port.container_port,
            public_port=self.run_spec.configuration.port.local_port,
        )

    def _shell_commands(self) -> List[str]:
        return self.run_spec.configuration.commands

    def _default_max_duration(self) -> Optional[int]:
        return None

    def _retry_policy(self) -> RetryPolicy:
        # convert ProfileRetryPolicy to RetryPolicy
        return RetryPolicy.parse_obj(self.run_spec.profile.retry_policy)

    def _spot_policy(self) -> SpotPolicy:
        return self.run_spec.profile.spot_policy or SpotPolicy.AUTO

    def _ports(self) -> List[PortMapping]:
        return []
