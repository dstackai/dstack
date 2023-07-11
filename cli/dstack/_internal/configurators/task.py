from typing import List, Optional

from dstack._internal.configurators import JobConfigurator, validate_local_path
from dstack._internal.configurators.extensions.ssh import SSHd
from dstack._internal.configurators.ports import get_map_to_port
from dstack._internal.core import job as job
from dstack._internal.core.configuration import TaskConfiguration
from dstack._internal.core.repo import Repo


class TaskConfigurator(JobConfigurator):
    conf: TaskConfiguration
    sshd: Optional[SSHd]

    def get_jobs(
        self, repo: Repo, run_name: str, repo_code_filename: str, ssh_key_pub: str
    ) -> List[job.Job]:
        self.sshd = SSHd(ssh_key_pub)
        self.sshd.map_to_port = get_map_to_port(self.ports(), self.sshd.port)
        return super().get_jobs(repo, run_name, repo_code_filename, ssh_key_pub)

    def commands(self) -> List[str]:
        commands = []
        if self.conf.image is None:
            self.sshd.start(commands)
        commands.extend(self.conf.commands)
        return commands

    def optional_build_commands(self) -> List[str]:
        return []  # not needed

    def artifact_specs(self) -> List[job.ArtifactSpec]:
        specs = []
        for a in self.conf.artifacts:
            specs.append(
                job.ArtifactSpec(
                    artifact_path=validate_local_path(a.path, self.home_dir(), self.working_dir),
                    mount=a.mount,
                )
            )
        return specs

    def dep_specs(self) -> List[job.DepSpec]:
        return []  # not available yet

    def app_specs(self) -> List[job.AppSpec]:
        specs = super().app_specs()
        if self.conf.image is None:
            self.sshd.add_app(specs)
        return specs
