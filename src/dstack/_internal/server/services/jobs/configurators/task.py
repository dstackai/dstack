from typing import List, Optional

from dstack._internal.core.models.configurations import (
    NodeGroup,
    PortMapping,
    RunConfigurationType,
)
from dstack._internal.core.models.profiles import SpotPolicy
from dstack._internal.core.models.runs import JobSpec
from dstack._internal.server.services.jobs.configurators.base import (
    JobConfigurator,
    NodeGroupJobContext,
)


class TaskJobConfigurator(JobConfigurator):
    TYPE: RunConfigurationType = RunConfigurationType.TASK

    async def get_job_specs(self, replica_num: int) -> List[JobSpec]:
        assert self.run_spec.configuration.type == "task"
        groups = self.run_spec.configuration.node_groups
        total = sum(group.nodes for group in groups)

        job_specs = []
        job_num = 0
        for group_index, group in enumerate(groups):
            for local_index in range(group.nodes):
                job_spec = await self._get_job_spec(
                    replica_num=replica_num,
                    job_num=job_num,
                    jobs_per_replica=total,
                    node_group_context=NodeGroupJobContext(
                        group=group,
                        group_index=group_index,
                        job_index=local_index,
                    ),
                )
                job_specs.append(job_spec)
                job_num += 1
        return job_specs

    def _shell_commands(self, node_group: Optional[NodeGroup] = None) -> List[str]:
        assert node_group is not None
        return node_group.commands

    def _default_single_branch(self) -> bool:
        return True

    def _default_max_duration(self) -> Optional[int]:
        return None

    def _spot_policy(self) -> SpotPolicy:
        return self.run_spec.merged_profile.spot_policy or SpotPolicy.ONDEMAND

    def _ports(self, node_group: Optional[NodeGroup] = None) -> List[PortMapping]:
        assert node_group is not None
        return node_group.ports
