from typing import List, Optional

from dstack._internal.configurators import JobConfiguratorWithPorts, validate_local_path
from dstack._internal.configurators.extensions.ssh import SSHd
from dstack._internal.configurators.ports import get_map_to_port
from dstack._internal.core import job as job
from dstack._internal.core.configuration import TaskConfiguration
from dstack._internal.core.plan import RunPlan
from dstack._internal.core.repo import Repo

DEFAULT_MAX_DURATION_SECONDS = 72 * 3600


class TaskConfigurator(JobConfiguratorWithPorts):
    conf: TaskConfiguration
    sshd: Optional[SSHd]

    def get_jobs(
        self,
        repo: Repo,
        run_name: str,
        repo_code_filename: str,
        ssh_key_pub: str,
        run_plan: Optional[RunPlan] = None,
    ) -> List[job.Job]:
        self.sshd = SSHd(ssh_key_pub)
        self.sshd.map_to_port = get_map_to_port(self.ports(), self.sshd.port)
        return super().get_jobs(repo, run_name, repo_code_filename, ssh_key_pub, run_plan)

    def build_commands(self) -> List[str]:
        return self.conf.build

    def setup(self) -> List[str]:
        commands = []
        if self.conf.image is None:
            commands += self.sshd.get_setup_commands()
        commands += self.conf.setup
        return commands

    def commands(self) -> List[str]:
        commands = []
        if self.conf.image is None:
            commands += self.sshd.get_start_commands()
        commands += self.conf.commands
        return commands

    def default_max_duration(self) -> Optional[int]:
        return DEFAULT_MAX_DURATION_SECONDS

    def termination_policy(self) -> job.TerminationPolicy:
        return self.profile.termination_policy or job.TerminationPolicy.TERMINATE

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
            specs.append(self.sshd.get_app_spec())
        return specs
