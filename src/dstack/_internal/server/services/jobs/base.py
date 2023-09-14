import shlex
import sys
from abc import ABC, abstractmethod
from typing import Dict, List, Optional

import dstack.version as version
from dstack._internal.core.models.configurations import (
    ConfigurationType,
    PythonVersion,
    RegistryAuth,
)
from dstack._internal.core.models.profiles import SpotPolicy
from dstack._internal.core.models.runs import (
    AppSpec,
    Gateway,
    Job,
    Requirements,
    RetryPolicy,
    RunSpec,
)


class JobConfigurator(ABC):
    TYPE: ConfigurationType

    def __init__(self, run_spec: RunSpec):
        self.run_spec = run_spec

    @abstractmethod
    def commands(self) -> List[str]:
        pass

    @abstractmethod
    def gateway(self) -> Optional[Gateway]:
        pass

    @abstractmethod
    def max_duration(self) -> Optional[int]:
        pass

    @abstractmethod
    def requirements(self) -> Requirements:
        pass

    @abstractmethod
    def retry_policy(self) -> RetryPolicy:
        pass

    @abstractmethod
    def spot_policy(self) -> SpotPolicy:
        pass

    @abstractmethod
    def app_specs(self) -> List[AppSpec]:
        pass

    def entrypoint(self) -> Optional[List[str]]:
        if self.run_spec.configuration.entrypoint is not None:
            return shlex.split(self.run_spec.configuration.entrypoint)
        if self.run_spec.configuration.image is None:  # dstackai/base
            return ["/bin/bash", "-i", "-c"]
        if self.commands():  # custom docker image with commands
            return ["/bin/sh", "-i", "-c"]
        return None

    def env(self) -> Dict[str, str]:
        return self.run_spec.configuration.env

    def home_dir(self) -> Optional[str]:
        return self.run_spec.configuration.home_dir

    def image_name(self) -> str:
        if self.run_spec.configuration.image is not None:
            return self.run_spec.configuration.image
        return f"dstackai/base:py{self.python()}-{version.base_image}-cuda-11.8"

    def registry_auth(self) -> Optional[RegistryAuth]:
        return self.run_spec.configuration.registry_auth

    def working_dir(self) -> str:
        return self.run_spec.working_dir

    def _python(self) -> str:
        if self.run_spec.configuration.python is not None:
            return self.run_spec.configuration.python.value
        version_info = sys.version_info
        return PythonVersion(f"{version_info.major}.{version_info.minor}").value
