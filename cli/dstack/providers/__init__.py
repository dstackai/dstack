import importlib
import sys
import time
from abc import abstractmethod
from argparse import ArgumentParser, Namespace
from pkgutil import iter_modules
from typing import Any, Dict, List, Optional, Union

from jinja2 import Template

from dstack.api.repo import load_repo_data
from dstack.backend.base import Backend
from dstack.core.job import (
    ArtifactSpec,
    DepSpec,
    GpusRequirements,
    Job,
    JobSpec,
    JobStatus,
    Requirements,
)
from dstack.core.repo import RepoAddress, RepoData
from dstack.utils.common import _quoted

DEFAULT_CPU = 2
DEFAULT_MEM = "8GB"


def _str_to_mib(s: str) -> int:
    ns = s.replace(" ", "").lower()
    if ns.endswith("mib"):
        return int(s[:-3])
    elif ns.endswith("gib"):
        return int(s[:-3]) * 1024
    elif ns.endswith("mi"):
        return int(s[:-2])
    elif ns.endswith("gi"):
        return int(s[:-2]) * 1024
    elif ns.endswith("mb"):
        return int(int(s[:-2]) * 1000 * 1000 / 1024 / 1024)
    elif ns.endswith("gb"):
        return int(int(s[:-2]) * (1000 * 1000 * 1000) / 1024 / 1024)
    elif ns.endswith("m"):
        return int(int(s[:-1]) * 1000 * 1000 / 1024 / 1024)
    elif ns.endswith("g"):
        return int(int(s[:-1]) * (1000 * 1000 * 1000) / 1024 / 1024)
    else:
        raise Exception(f"Unknown memory unit: {s}")


class Provider:
    def __init__(self, provider_name: str):
        self.provider_name: str = provider_name
        self.provider_data: Optional[Dict[str, Any]] = None
        self.provider_args: Optional[List[str]] = None
        self.workflow_name: Optional[str] = None
        self.run_as_provider: Optional[bool] = None
        self.run_name: Optional[str] = None
        self.dep_specs: Optional[List[DepSpec]] = None
        self.loaded = False

    def __str__(self) -> str:
        return (
            f'Provider(name="{self.provider_name}", '
            f'workflow_data="{self.provider_data}", '
            f'workflow_name="{_quoted(self.workflow_name)}, '
            f'provider_name="{self.provider_name}", '
            f"run_as_provider={self.run_as_provider})"
        )

    # TODO: This is a dirty hack
    def _safe_python_version(self, name: str):
        python_version: str
        v = self.provider_data.get(name)
        if isinstance(v, str):
            python_version = v
        elif v == 3.1:
            python_version = "3.10"
        elif v:
            python_version = str(v)
        else:
            version_info = sys.version_info
            python_version = f"{version_info.major}.{version_info.minor}"
        supported_python_versions = ["3.7", "3.8", "3.9", "3.10", "3.11"]
        if python_version not in supported_python_versions:
            sys.exit(
                f"Python version `{python_version}` is not supported. "
                f"Supported versions: {str(supported_python_versions)}."
            )
        return python_version

    def _inject_context(self):
        class Args:
            def __init__(self, args: List[str]) -> None:
                super().__init__()
                self.args = args

            def __str__(self):
                _str = ""
                for arg in self.args:
                    if _str:
                        _str += " "
                    if " " in arg:
                        _str += '"' + arg.replace('"', '\\"') + '"'
                    else:
                        _str += arg
                return _str

        class Run:
            def __init__(self, name: str, args: Args) -> None:
                super().__init__()
                self.name = name
                self.args = args

        run = Run(self.run_name, Args(self.provider_data.get("run_args") or []))
        self.provider_data = self._inject_context_recursively(self.provider_data, run=run)

    @staticmethod
    def _inject_context_recursively(obj: Any, **kwargs: Any) -> Any:
        if isinstance(obj, str):
            return Template(obj, variable_start_string="${{").render(**kwargs)
        elif isinstance(obj, dict):
            d = {}
            for k in obj:
                d[k] = Provider._inject_context_recursively(obj[k], **kwargs)
            return d
        elif isinstance(obj, list):
            return [Provider._inject_context_recursively(item, **kwargs) for item in obj]
        else:
            return obj

    def load(
        self,
        backend: Backend,
        provider_args: List[str],
        workflow_name: Optional[str],
        provider_data: Dict[str, Any],
        run_name: str,
    ):
        self.provider_args = provider_args
        self.workflow_name = workflow_name
        self.provider_data = provider_data
        self.run_as_provider = not workflow_name
        self.run_name = run_name
        self.parse_args()
        self._inject_context()
        self.dep_specs = self._dep_specs(backend)
        self.loaded = True

    @abstractmethod
    def _create_parser(self, workflow_name: Optional[str]) -> Optional[ArgumentParser]:
        return None

    def help(self, workflow_name: Optional[str]):
        parser = self._create_parser(workflow_name)
        if parser:
            parser.print_help()

    @abstractmethod
    def create_job_specs(self) -> List[JobSpec]:
        pass

    @staticmethod
    def _add_base_args(parser: ArgumentParser):
        parser.add_argument("-r", "--requirements", metavar="PATH", type=str)
        parser.add_argument("-e", "--env", action="append")
        parser.add_argument("-a", "--artifact", metavar="PATH", dest="artifacts", action="append")
        parser.add_argument("--dep", metavar="(:TAG | WORKFLOW)", dest="deps", action="append")
        parser.add_argument("-w", "--working-dir", metavar="PATH", type=str)
        group = parser.add_mutually_exclusive_group()
        group.add_argument("-i", "--interruptible", action="store_true")
        group.add_argument("-l", "--local", action="store_true")
        parser.add_argument("--cpu", metavar="NUM", type=int)
        parser.add_argument("--memory", metavar="SIZE", type=str)
        parser.add_argument("--gpu", metavar="NUM", type=int)
        parser.add_argument("--gpu-name", metavar="NAME", type=str)
        parser.add_argument("--gpu-memory", metavar="SIZE", type=str)
        parser.add_argument("--shm-size", metavar="SIZE", type=str)

    def _parse_base_args(self, args: Namespace, unknown_args):
        if args.requirements:
            self.provider_data["requirements"] = args.requirements
        if args.artifacts:
            self.provider_data["artifacts"] = args.artifacts
        if args.deps:
            self.provider_data["deps"] = args.deps
        if args.working_dir:
            self.provider_data["working_dir"] = args.working_dir
        if args.env:
            env = self.provider_data.get("env") or []
            env.extend(args.env)
            self.provider_data["env"] = env

        resources = self.provider_data.get("resources") or {}
        self.provider_data["resources"] = resources
        if args.cpu:
            resources["cpu"] = args.cpu
        if args.memory:
            resources["memory"] = args.memory
        if args.gpu or args.gpu_name or args.gpu_memory:
            gpu = (
                self.provider_data["resources"].get("gpu") or {}
                if self.provider_data.get("resources")
                else {}
            )
            if type(gpu) is int:
                gpu = {"count": gpu}
            resources["gpu"] = gpu
            if args.gpu:
                gpu["count"] = args.gpu
            if args.gpu_memory:
                gpu["memory"] = args.gpu_memory
            if args.gpu_name:
                gpu["name"] = args.gpu_name
        if args.shm_size:
            resources["shm_size"] = args.shm_size
        if args.interruptible:
            resources["interruptible"] = True
        if args.local:
            resources["local"] = True
        if unknown_args:
            self.provider_data["run_args"] = unknown_args

    def parse_args(self):
        pass

    def submit_jobs(self, backend: Backend, tag_name: str) -> List[Job]:
        if not self.loaded:
            raise Exception("The provider is not loaded")
        job_specs = self.create_job_specs()
        repo_data = load_repo_data()
        # [TODO] Handle master job
        jobs = []
        for i, job_spec in enumerate(job_specs):
            submitted_at = int(round(time.time() * 1000))
            job = Job(
                job_id=f"{self.run_name},{self.workflow_name or ''},{i}",
                repo_data=repo_data,
                run_name=self.run_name,
                workflow_name=self.workflow_name or None,
                provider_name=self.provider_name,
                local_repo_user_name=repo_data.local_repo_user_name,
                local_repo_user_email=repo_data.local_repo_user_email,
                status=JobStatus.SUBMITTED,
                submitted_at=submitted_at,
                image_name=job_spec.image_name,
                commands=job_spec.commands,
                env=job_spec.env,
                working_dir=job_spec.working_dir,
                artifact_specs=job_spec.artifact_specs,
                port_count=job_spec.port_count,
                ports=None,
                host_name=None,
                requirements=job_spec.requirements,
                dep_specs=self.dep_specs,
                master_job=job_spec.master_job,
                app_specs=job_spec.app_specs,
                runner_id=None,
                request_id=None,
                tag_name=tag_name,
            )
            backend.submit_job(job)
            jobs.append(job)
        if tag_name:
            backend.add_tag_from_run(repo_data, tag_name, self.run_name, jobs)
        return jobs

    def _dep_specs(self, backend: Backend) -> Optional[List[DepSpec]]:
        if self.provider_data.get("deps"):
            repo_data = load_repo_data()
            return [
                self._parse_dep_spec(dep, backend, repo_data) for dep in self.provider_data["deps"]
            ]
        else:
            return None

    def _artifact_specs(self) -> Optional[List[ArtifactSpec]]:
        if self.provider_data.get("artifacts"):
            return [self._parse_artifact_spec(a) for a in self.provider_data["artifacts"]]
        else:
            return None

    @staticmethod
    def _parse_artifact_spec(artifact: Union[dict, str]) -> ArtifactSpec:
        def remove_prefix(text: str, prefix: str) -> str:
            if text.startswith(prefix):
                return text[len(prefix) :]
            return text

        if isinstance(artifact, str):
            return ArtifactSpec(artifact_path=remove_prefix(artifact, "./"), mount=False)
        else:
            return ArtifactSpec(
                artifact_path=remove_prefix(artifact["path"], "./"),
                mount=artifact.get("mount") is True,
            )

    @staticmethod
    def _parse_dep_spec(dep: Union[dict, str], backend: Backend, repo_data: RepoData) -> DepSpec:
        if isinstance(dep, str):
            mount = False
            if dep.startswith(":"):
                tag_dep = True
                dep = dep[1:]
            else:
                tag_dep = False
        else:
            mount = dep.get("mount") is True
            tag_dep = dep.get("tag") is not None
            dep = dep.get("tag") or dep.get("workflow")
        t = dep.split("/")
        if len(t) == 1:
            if tag_dep:
                return Provider._tag_dep(backend, repo_data, t[0], mount)
            else:
                return Provider._workflow_dep(backend, repo_data, t[0], mount)
        elif len(t) == 3:
            # This doesn't allow to refer to projects from other repos
            repo_address = RepoAddress(
                repo_host_name=repo_data.repo_host_name,
                repo_port=repo_data.repo_port,
                repo_user_name=t[0],
                repo_name=t[1],
            )
            if tag_dep:
                return Provider._tag_dep(backend, repo_address, t[2], mount)
            else:
                return Provider._workflow_dep(backend, repo_address, t[2], mount)
        else:
            sys.exit(f"Invalid dep format: {dep}")

    @staticmethod
    def _tag_dep(
        backend: Backend, repo_address: RepoAddress, tag_name: str, mount: bool
    ) -> DepSpec:
        tag_head = backend.get_tag_head(repo_address, tag_name)
        if tag_head:
            return DepSpec(repo_address=repo_address, run_name=tag_head.run_name, mount=mount)
        else:
            sys.exit(f"Cannot find the tag '{tag_name}' in the '{repo_address.path()}' repo")

    @staticmethod
    def _workflow_dep(
        backend: Backend, repo_address: RepoAddress, workflow_name: str, mount: bool
    ) -> DepSpec:
        job_heads = sorted(
            backend.list_job_heads(repo_address),
            key=lambda j: j.submitted_at,
            reverse=True,
        )
        run_name = next(
            iter(
                [
                    job_head.run_name
                    for job_head in job_heads
                    if job_head.workflow_name == workflow_name
                    and job_head.status == JobStatus.DONE
                ]
            ),
            None,
        )
        if run_name:
            return DepSpec(repo_address=repo_address, run_name=run_name, mount=mount)
        else:
            sys.exit(
                f"Cannot find any successful workflow with the name '{workflow_name}' "
                f"in the '{repo_address.path()}' repo"
            )

    def _env(self) -> Optional[Dict[str, str]]:
        if self.provider_data.get("env"):
            env = {}
            for e in self.provider_data.get("env"):
                if "=" in e:
                    tokens = e.split("=", maxsplit=1)
                    env[tokens[0]] = tokens[1]
                else:
                    env[e] = ""
            return env
        else:
            return None

    def _get_list_data(self, name: str) -> Optional[List[str]]:
        v = self.provider_data.get(name)
        if isinstance(v, str):
            return v.split("\n")
        else:
            return v

    def _resources(self) -> Requirements:
        resources = Requirements()
        cpu = self.provider_data["resources"].get("cpu", DEFAULT_CPU)
        if not str(cpu).isnumeric():
            sys.exit("resources.cpu should be an integer")
        cpu = int(cpu)
        if cpu > 0:
            resources.cpus = cpu
        memory = self.provider_data["resources"].get("memory", DEFAULT_MEM)
        resources.memory_mib = _str_to_mib(memory)
        gpu = self.provider_data["resources"].get("gpu")
        if gpu:
            if str(gpu).isnumeric():
                gpu = int(self.provider_data["resources"]["gpu"])
                if gpu > 0:
                    resources.gpus = GpusRequirements(count=gpu)
            else:
                gpu_count = 0
                gpu_name = None
                if str(gpu.get("count")).isnumeric():
                    gpu_count = int(gpu.get("count"))
                if gpu.get("name"):
                    gpu_name = gpu.get("name")
                    if not gpu_count:
                        gpu_count = 1
                if gpu_count:
                    resources.gpus = GpusRequirements(count=gpu_count, name=gpu_name)
        for resource_name in self.provider_data["resources"]:
            if resource_name.endswith("/gpu") and len(resource_name) > 4:
                if not str(self.provider_data["resources"][resource_name]).isnumeric():
                    sys.exit(f"resources.'{resource_name}' should be an integer")
                gpu = int(self.provider_data["resources"][resource_name])
                if gpu > 0:
                    resources.gpus = GpusRequirements(count=gpu, name=resource_name[:-4])
        if self.provider_data["resources"].get("shm_size"):
            resources.shm_size_mib = _str_to_mib(self.provider_data["resources"]["shm_size"])
        if self.provider_data["resources"].get("interruptible"):
            resources.interruptible = self.provider_data["resources"]["interruptible"]
        if self.provider_data["resources"].get("local"):
            resources.local = self.provider_data["resources"]["local"]
        return resources

    @staticmethod
    def _extend_commands_with_env(commands, env):
        commands.extend([f"export {e}={env[e] if env.get(e) else ''}" for e in env])


def get_provider_names() -> List[str]:
    return list(
        map(
            lambda m: m[1],
            filter(
                lambda m: m.ispkg and not m[1].startswith("_"),
                iter_modules(sys.modules[__name__].__path__),
            ),
        )
    )


def load_provider(provider_name) -> Provider:
    return importlib.import_module(f"dstack.providers.{provider_name}.main").__provider__()
