from typing import List, Optional

from dstack._internal.core.models.configurations import PortMapping, RunConfigurationType
from dstack._internal.core.models.profiles import SpotPolicy
from dstack._internal.core.models.runs import JobSpec
from dstack._internal.server.services.jobs.configurators.base import JobConfigurator

DEFAULT_MAX_DURATION_SECONDS = 72 * 3600


class TaskJobConfigurator(JobConfigurator):
    TYPE: RunConfigurationType = RunConfigurationType.TASK

    async def get_job_specs(self, replica_num: int) -> List[JobSpec]:
        job_specs = []
        for job_num in range(self.run_spec.configuration.nodes):
            job_spec = await self._get_job_spec(
                replica_num=replica_num,
                job_num=job_num,
                jobs_per_replica=self.run_spec.configuration.nodes,
            )
            job_specs.append(job_spec)
        return job_specs

    def _shell_commands(self) -> List[str]:
        return self.run_spec.configuration.commands

    def _default_max_duration(self) -> Optional[int]:
        return DEFAULT_MAX_DURATION_SECONDS

    def _spot_policy(self) -> SpotPolicy:
        return self.run_spec.merged_profile.spot_policy or SpotPolicy.AUTO

    def _ports(self) -> List[PortMapping]:
        return self.run_spec.configuration.ports

    def _working_dir(self) -> Optional[str]:
        return None if not self._shell_commands() else super()._working_dir()
