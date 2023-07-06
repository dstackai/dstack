from typing import List

from dstack._internal.configurators import JobConfigurator
from dstack._internal.core import job as job
from dstack._internal.core.configuration import TaskConfiguration


class TaskConfigurator(JobConfigurator):
    conf: TaskConfiguration

    def commands(self) -> List[str]:
        commands = []
        commands.extend(self.conf.commands)
        return commands

    def optional_build_commands(self) -> List[str]:
        return []  # not needed

    def artifact_specs(self) -> List[job.ArtifactSpec]:
        specs = []
        for a in self.conf.artifacts:
            specs.append(job.ArtifactSpec(artifact_path=a.path, mount=a.mount))
        return specs

    def dep_specs(self) -> List[job.DepSpec]:
        return []  # not available yet
