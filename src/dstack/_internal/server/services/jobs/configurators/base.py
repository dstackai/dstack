import shlex
import sys
from abc import ABC, abstractmethod
from typing import Dict, List, Optional

import dstack.version as version
from dstack._internal.core.models.configurations import (
    ConfigurationType,
    PortMapping,
    PythonVersion,
    RegistryAuth,
)
from dstack._internal.core.models.profiles import SpotPolicy
from dstack._internal.core.models.runs import (
    AppSpec,
    Gateway,
    GpusRequirements,
    JobSpec,
    Requirements,
    RetryPolicy,
    RunSpec,
)
from dstack._internal.core.services.ssh.ports import filter_reserved_ports


class JobConfigurator(ABC):
    TYPE: ConfigurationType

    def __init__(self, run_spec: RunSpec):
        self.run_spec = run_spec

    def get_job_specs(self) -> List[JobSpec]:
        job_spec = JobSpec(
            job_num=0,
            job_name=self.run_spec.run_name + "-0",
            app_specs=self._app_specs(),
            commands=self._commands(),
            env=self._env(),
            gateway=self._gateway(),
            home_dir=self._home_dir(),
            image_name=self._image_name(),
            max_duration=self._max_duration(),
            registry_auth=self._registry_auth(),
            requirements=self._requirements(),
            retry_policy=self._retry_policy(),
            working_dir=self._working_dir(),
        )
        return [job_spec]

    @abstractmethod
    def _shell_commands(self) -> List[str]:
        pass

    @abstractmethod
    def _default_max_duration(self) -> Optional[int]:
        pass

    @abstractmethod
    def _retry_policy(self) -> RetryPolicy:
        pass

    @abstractmethod
    def _spot_policy(self) -> SpotPolicy:
        pass

    @abstractmethod
    def _ports(self) -> List[PortMapping]:
        pass

    def _commands(self) -> List[str]:
        if self.run_spec.configuration.entrypoint is not None:  # docker-like format
            entrypoint = shlex.split(self.run_spec.configuration.entrypoint)
            commands = self.run_spec.configuration.commands
        elif self.run_spec.configuration.image is None:  # dstackai/base
            entrypoint = ["/bin/bash", "-i", "-c"]
            commands = [_join_shell_commands(self._shell_commands())]
        elif self._shell_commands():  # custom docker image with shell commands
            entrypoint = ["/bin/sh", "-i", "-c"]
            commands = [_join_shell_commands(self._shell_commands())]
        else:  # custom docker image without commands
            raise NotImplemented()  # TODO read docker image manifest
        return entrypoint + commands

    def _app_specs(self) -> List[AppSpec]:
        specs = []
        for i, pm in enumerate(filter_reserved_ports(self._ports())):
            specs.append(
                AppSpec(
                    port=pm.container_port,
                    map_to_port=pm.local_port,
                    app_name=f"app_{i}",
                )
            )
        return specs

    def _entrypoint(self) -> Optional[List[str]]:
        if self.run_spec.configuration.entrypoint is not None:
            return shlex.split(self.run_spec.configuration.entrypoint)
        if self.run_spec.configuration.image is None:  # dstackai/base
            return ["/bin/bash", "-i", "-c"]
        if self._commands():  # custom docker image with commands
            return ["/bin/sh", "-i", "-c"]
        return None

    def _env(self) -> Dict[str, str]:
        return self.run_spec.configuration.env

    def _gateway(self) -> Optional[Gateway]:
        return None

    def _home_dir(self) -> Optional[str]:
        return self.run_spec.configuration.home_dir

    def _image_name(self) -> str:
        if self.run_spec.configuration.image is not None:
            return self.run_spec.configuration.image
        # TODO: non-cuda image
        return f"dstackai/base:py{self._python()}-{version.base_image}-cuda-11.8"

    def _max_duration(self) -> Optional[int]:
        if self.run_spec.profile.max_duration is None:
            return self._default_max_duration()
        if self.run_spec.profile.max_duration == "off":
            return None
        return self.run_spec.profile.max_duration

    def _registry_auth(self) -> Optional[RegistryAuth]:
        return self.run_spec.configuration.registry_auth

    def _requirements(self) -> Requirements:
        spot_policy = self._spot_policy()
        r = Requirements(
            cpus=self.run_spec.profile.resources.cpu,
            memory_mib=self.run_spec.profile.resources.memory,
            gpus=None,
            shm_size_mib=self.run_spec.profile.resources.shm_size,
            max_price=self.run_spec.profile.max_price,
            spot=None if spot_policy == SpotPolicy.AUTO else (spot_policy == SpotPolicy.SPOT),
        )
        if self.run_spec.profile.resources.gpu:
            r.gpus = GpusRequirements(
                count=self.run_spec.profile.resources.gpu.count,
                memory_mib=self.run_spec.profile.resources.gpu.memory,
                name=self.run_spec.profile.resources.gpu.name,
                total_memory_mib=self.run_spec.profile.resources.gpu.total_memory,
                compute_capability=self.run_spec.profile.resources.gpu.compute_capability,
            )
        return r

    def _working_dir(self) -> str:
        return self.run_spec.working_dir

    def _python(self) -> str:
        if self.run_spec.configuration.python is not None:
            return self.run_spec.configuration.python.value
        version_info = sys.version_info
        return PythonVersion(f"{version_info.major}.{version_info.minor}").value


def _join_shell_commands(commands: List[str], env: Optional[Dict[str, str]] = None) -> str:
    if env is None:
        env = {}
    commands = [f"export {k}={v}" for k, v in env.items()] + commands
    for i, cmd in enumerate(commands):
        cmd = cmd.strip()
        if cmd.endswith("&"):  # escape background command
            cmd = "{ %s }" % cmd
        commands[i] = cmd
    return " && ".join(commands)
