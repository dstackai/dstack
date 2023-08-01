from typing import Dict, List, Optional

import dstack._internal.configurators.ports as ports
import dstack._internal.core.job as job
from dstack._internal.configurators import JobConfigurator
from dstack._internal.core.configuration import ServiceConfiguration


class ServiceConfigurator(JobConfigurator):
    conf: ServiceConfiguration

    def commands(self) -> List[str]:
        return self.conf.commands

    def artifact_specs(self) -> List[job.ArtifactSpec]:
        return []  # not implemented

    def dep_specs(self) -> List[job.DepSpec]:
        return []  # not implemented

    def default_max_duration(self) -> Optional[int]:
        return None  # infinite

    def ports(self) -> Dict[int, ports.PortMapping]:
        port = self.conf.port.container_port
        return {port: ports.PortMapping(container_port=port)}

    def gateway(self) -> Optional[job.Gateway]:
        return job.Gateway(
            hostname=self.conf.gateway,
            service_port=self.conf.port.container_port,
            public_port=self.conf.port.local_port,
        )

    def build_commands(self) -> List[str]:
        return self.conf.build

    def setup(self) -> List[str]:
        return self.conf.setup

    def termination_policy(self) -> job.TerminationPolicy:
        return self.profile.termination_policy or job.TerminationPolicy.TERMINATE
