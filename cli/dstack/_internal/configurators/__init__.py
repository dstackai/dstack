import argparse
import json
import shlex
import sys
import uuid
from abc import ABC, abstractmethod
from typing import Dict, List, Optional

from rich_argparse import RichHelpFormatter

import dstack._internal.configurators.ports as ports
import dstack._internal.core.job as job
import dstack.version as version
from dstack._internal.configurators.cli import env_var, gpu_resource, port_mapping
from dstack._internal.core.build import BuildPolicy
from dstack._internal.core.configuration import (
    BaseConfiguration,
    BaseConfigurationWithPorts,
    PythonVersion,
)
from dstack._internal.core.error import DstackError
from dstack._internal.core.plan import RunPlan
from dstack._internal.core.profile import GPU, Profile, parse_duration, parse_max_duration
from dstack._internal.core.repo import Repo
from dstack._internal.utils.common import get_milliseconds_since_epoch
from dstack._internal.utils.interpolator import VariablesInterpolator


class JobConfigurator(ABC):
    def __init__(
        self,
        working_dir: str,
        configuration_path: str,
        configuration: BaseConfiguration,
        profile: Profile,
    ):
        self.configuration_path = configuration_path
        self.working_dir = working_dir
        self.conf = configuration
        self.profile = profile
        self.build_policy = BuildPolicy.USE_BUILD
        # context
        self.run_name: Optional[str] = None
        self.ssh_key_pub: Optional[str] = None

    def get_parser(
        self, prog: Optional[str] = None, parser: Optional[argparse.ArgumentParser] = None
    ) -> argparse.ArgumentParser:
        if parser is None:
            parser = argparse.ArgumentParser(prog=prog, formatter_class=RichHelpFormatter)

        parser.add_argument(
            "--backend",
            action="append",
            dest="backends",
            help="The backends that will be tried for provisioning",
        )

        parser.add_argument(
            "-e", "--env", type=env_var, action="append", help="Environmental variable"
        )

        parser.add_argument(
            "--gpu",
            metavar="NAME:COUNT:MEMORY",
            type=gpu_resource,
            help="Request a GPU for the run",
        )

        parser.add_argument(
            "--max-price",
            metavar="PRICE",
            type=float,
            help="The maximum price per hour, in dollars",
        )

        spot_group = parser.add_mutually_exclusive_group()
        spot_group.add_argument(
            "--spot", action="store_const", dest="spot_policy", const=job.SpotPolicy.SPOT
        )
        spot_group.add_argument(
            "--on-demand", action="store_const", dest="spot_policy", const=job.SpotPolicy.ONDEMAND
        )
        spot_group.add_argument(
            "--spot-auto", action="store_const", dest="spot_policy", const=job.SpotPolicy.AUTO
        )
        spot_group.add_argument("--spot-policy", type=job.SpotPolicy, dest="spot_policy")

        retry_group = parser.add_mutually_exclusive_group()
        retry_group.add_argument("--retry", action="store_true")
        retry_group.add_argument("--no-retry", action="store_true")
        retry_group.add_argument("--retry-limit", type=str)

        parser.add_argument("--max-duration", type=str)

        build_policy = parser.add_mutually_exclusive_group()
        build_policy.add_argument(
            "--build", action="store_const", dest="build_policy", const=BuildPolicy.BUILD
        )
        build_policy.add_argument(
            "--force-build",
            action="store_const",
            dest="build_policy",
            const=BuildPolicy.FORCE_BUILD,
        )

        return parser

    def apply_args(self, args: argparse.Namespace):
        if args.backends is not None:
            self.profile.backends = args.backends

        if args.env is not None:
            for key, value in args.env:
                self.conf.env[key] = value

        if args.gpu is not None:
            gpu = (self.profile.resources.gpu or GPU()).dict(exclude_defaults=True)
            gpu.update(args.gpu)
            self.profile.resources.gpu = GPU.parse_obj(gpu)

        if args.max_price is not None:
            self.profile.max_price = args.max_price

        if args.spot_policy is not None:
            self.profile.spot_policy = args.spot_policy

        if args.retry:
            self.profile.retry_policy.retry = True
        elif args.no_retry:
            self.profile.retry_policy.retry = False
        elif args.retry_limit:
            self.profile.retry_policy.retry = True
            self.profile.retry_policy.limit = parse_duration(args.retry_limit)

        if args.build_policy is not None:
            self.build_policy = args.build_policy

        if args.max_duration:
            self.profile.max_duration = parse_max_duration(args.max_duration)

    def inject_context(
        self, namespaces: Dict[str, Dict[str, str]], skip: Optional[List[str]] = None
    ):
        if skip is None:
            skip = ["secrets"]
        vi = VariablesInterpolator(namespaces, skip=skip)

        def interpolate(obj):
            if isinstance(obj, str):
                return vi.interpolate(obj)
            if isinstance(obj, dict):
                return {k: interpolate(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [interpolate(i) for i in obj]
            return obj

        conf = json.loads(self.conf.json())
        conf = interpolate(conf)
        self.conf = type(self.conf).parse_obj(conf)

    def get_jobs(
        self,
        repo: Repo,
        run_name: str,
        repo_code_filename: str,
        ssh_key_pub: str,
        run_plan: Optional[RunPlan] = None,
    ) -> List[job.Job]:
        self.run_name = run_name
        self.ssh_key_pub = ssh_key_pub
        created_at = get_milliseconds_since_epoch()
        configured_job = job.Job(
            app_specs=self.app_specs(),
            artifact_specs=self.artifact_specs(),
            backends=self.profile.backends,
            build_commands=self.build_commands(),
            build_policy=self.build_policy,
            cache_specs=self.cache_specs(),
            commands=self.commands(),
            configuration_path=self.configuration_path,
            configuration_type=job.ConfigurationType(self.conf.type),
            created_at=created_at,
            dep_specs=self.dep_specs(),
            entrypoint=self.entrypoint(),
            env=self.env(),
            gateway=self.gateway(),
            home_dir=self.home_dir(),
            image_name=self.image_name(run_plan),
            instance_name=f"dstack-{run_name}",
            job_id=f"{run_name},,0",
            max_duration=self.max_duration(),
            registry_auth=self.registry_auth(),
            repo_code_filename=repo_code_filename,
            repo_data=repo.repo_data,
            repo_ref=repo.repo_ref,
            requirements=self.requirements(),
            retry_policy=self.retry_policy(),
            run_name=run_name,
            runner_id=uuid.uuid4().hex,
            setup=self.setup(),
            spot_policy=self.spot_policy(),
            ssh_key_pub=ssh_key_pub,
            status=job.JobStatus.SUBMITTED,
            submitted_at=created_at,
            termination_policy=self.termination_policy(),
            working_dir=self.working_dir,
        )
        return [configured_job]

    @abstractmethod
    def build_commands(self) -> List[str]:
        pass

    @abstractmethod
    def setup(self) -> List[str]:
        pass

    @abstractmethod
    def commands(self) -> Optional[List[str]]:
        pass

    @abstractmethod
    def artifact_specs(self) -> List[job.ArtifactSpec]:
        pass

    @abstractmethod
    def dep_specs(self) -> List[job.DepSpec]:
        pass

    @abstractmethod
    def default_max_duration(self) -> Optional[int]:
        pass

    @abstractmethod
    def ports(self) -> Dict[int, ports.PortMapping]:
        pass

    @abstractmethod
    def termination_policy(self) -> job.TerminationPolicy:
        pass

    def entrypoint(self) -> Optional[List[str]]:
        if self.conf.entrypoint is not None:
            return shlex.split(self.conf.entrypoint)
        if self.conf.image is None:  # dstackai/base
            return ["/bin/bash", "-i", "-c"]
        if self.commands():  # custom docker image with commands
            return ["/bin/sh", "-i", "-c"]
        return None

    def home_dir(self) -> Optional[str]:
        return self.conf.home_dir

    def image_name(self, run_plan: Optional[RunPlan]) -> Optional[str]:
        if self.conf.image is not None:
            return self.conf.image
        if run_plan is not None:
            if (
                run_plan is None
                or len(run_plan.job_plans[0].candidates) == 0
                or len(run_plan.job_plans[0].candidates[0].instance.resources.gpus) > 0
            ):
                return f"dstackai/base:py{self.python()}-{version.base_image}-cuda-11.8"
        return f"dstackai/base:py{self.python()}-{version.base_image}"

    def cache_specs(self) -> List[job.CacheSpec]:
        return [
            job.CacheSpec(path=validate_local_path(path, self.home_dir(), self.working_dir))
            for path in self.conf.cache
        ]

    def registry_auth(self) -> Optional[job.RegistryAuth]:
        if self.conf.registry_auth is None:
            return None
        return job.RegistryAuth.parse_obj(self.conf.registry_auth)

    def app_specs(self) -> List[job.AppSpec]:
        specs = []
        for i, pm in enumerate(ports.filter_reserved_ports(self.ports())):
            specs.append(
                job.AppSpec(
                    port=pm.container_port,
                    map_to_port=pm.local_port,
                    app_name=f"app_{i}",
                )
            )
        return specs

    def python(self) -> str:
        if self.conf.python is not None:
            return self.conf.python.value
        version_info = sys.version_info
        return PythonVersion(f"{version_info.major}.{version_info.minor}").value

    def env(self) -> Dict[str, str]:
        return self.conf.env

    def requirements(self) -> job.Requirements:
        r = job.Requirements(
            cpus=self.profile.resources.cpu,
            memory_mib=self.profile.resources.memory,
            gpus=None,
            shm_size_mib=self.profile.resources.shm_size,
            max_price=self.profile.max_price,
        )
        if self.profile.resources.gpu:
            r.gpus = job.GpusRequirements(
                count=self.profile.resources.gpu.count,
                memory_mib=self.profile.resources.gpu.memory,
                name=self.profile.resources.gpu.name,
            )
        return r

    @classmethod
    def join_run_args(cls, args: List[str]) -> str:
        return " ".join(
            (arg if " " not in arg else '"%s"' % arg.replace('"', '\\"')) for arg in args
        )

    def spot_policy(self) -> job.SpotPolicy:
        return self.profile.spot_policy or job.SpotPolicy.AUTO

    def retry_policy(self) -> job.RetryPolicy:
        return job.RetryPolicy.parse_obj(self.profile.retry_policy)

    def max_duration(self) -> Optional[int]:
        if self.profile.max_duration is None:
            return self.default_max_duration()
        if self.profile.max_duration < 0:
            return None
        return self.profile.max_duration

    def gateway(self) -> Optional[job.Gateway]:
        return None


class JobConfiguratorWithPorts(JobConfigurator, ABC):
    conf: BaseConfigurationWithPorts

    def get_parser(
        self, prog: Optional[str] = None, parser: Optional[argparse.ArgumentParser] = None
    ) -> argparse.ArgumentParser:
        parser = super().get_parser(prog, parser)
        parser.add_argument(
            "-p", "--port", type=port_mapping, action="append", help="Exposed port or mapping"
        )
        return parser

    def apply_args(self, args: argparse.Namespace):
        super().apply_args(args)
        if args.port is not None:
            self.conf.ports = list(ports.merge_ports(self.conf.ports, args.port).values())

    def ports(self) -> Dict[int, ports.PortMapping]:
        ports.unique_ports_constraint([pm.container_port for pm in self.conf.ports])
        ports.unique_ports_constraint(
            [pm.local_port for pm in self.conf.ports if pm.local_port is not None],
            error="Mapped port {} is already in use",
        )
        return {pm.container_port: pm for pm in self.conf.ports}


def validate_local_path(path: str, home: Optional[str], working_dir: str) -> str:
    if path == "~" or path.startswith("~/"):
        if home is None:
            raise HomeDirUnsetError("home_dir is not defined, local path can't start with ~")
        path = home if path == "~" else f"{home}/{path[len('~/'):]}"
    while path.startswith("./"):
        path = path[len("./") :]
    if not path.startswith("/"):
        path = "/".join(
            ["/workflow", path] if working_dir == "." else ["/workflow", working_dir, path]
        )
    return path


class HomeDirUnsetError(DstackError):
    pass
