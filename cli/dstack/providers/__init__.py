import argparse
import importlib
import shlex
import sys
import tempfile
from abc import abstractmethod
from argparse import ArgumentParser, Namespace
from pkgutil import iter_modules
from typing import Any, Dict, List, Optional, Union

import dstack.api.hub as hub
from dstack.core.cache import CacheSpec
from dstack.core.error import RepoNotInitializedError
from dstack.core.job import (
    ArtifactSpec,
    DepSpec,
    GpusRequirements,
    Job,
    JobSpec,
    JobStatus,
    Requirements,
)
from dstack.providers.ports import PortMapping, merge_ports
from dstack.utils.common import get_milliseconds_since_epoch
from dstack.utils.interpolator import VariablesInterpolator

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
        self.cache_specs: List[CacheSpec] = []
        self.ssh_key_pub: Optional[str] = None
        self.openssh_server: bool = False
        self.loaded = False
        self.home_dir: Optional[str] = None
        self.ports: Dict[int, PortMapping] = {}

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
        args = []
        for arg in self.provider_data.get("run_args", []):
            if " " in arg:
                arg = '"%s"' % arg.replace('"', '\\"')
            args.append(arg)

        self.provider_data = self._inject_context_recursively(
            VariablesInterpolator(
                {"run": {"name": self.run_name, "args": " ".join(args)}}, skip=["secrets"]
            ),
            self.provider_data,
        )

    @staticmethod
    def _inject_context_recursively(interpolator: VariablesInterpolator, obj: Any) -> Any:
        if isinstance(obj, str):
            return interpolator.interpolate(obj)
        elif isinstance(obj, dict):
            d = {}
            for k in obj:
                d[k] = Provider._inject_context_recursively(interpolator, obj[k])
            return d
        elif isinstance(obj, list):
            return [Provider._inject_context_recursively(interpolator, item) for item in obj]
        else:
            return obj

    def load(
        self,
        hub_client: "hub.HubClient",
        args: Optional[Namespace],
        workflow_name: Optional[str],
        provider_data: Dict[str, Any],
        run_name: str,
        ssh_key_pub: Optional[str] = None,
    ):
        if getattr(args, "help", False):
            self.help(workflow_name)
            exit()  # todo: find a better place for this

        self.provider_args = [] if args is None else args.args + args.unknown
        self.workflow_name = workflow_name
        self.provider_data = provider_data
        self.run_as_provider = not workflow_name
        self.run_name = run_name
        self.ssh_key_pub = ssh_key_pub
        self.openssh_server = self.provider_data.get("ssh", False)

        self.parse_args()
        self.ports = self.provider_data.get("ports") or {}
        if not self.ssh_key_pub:
            if self.openssh_server or (
                hub_client.get_project_backend_type() != "local" and not args.detach
            ):
                raise RepoNotInitializedError(
                    "No valid SSH identity", project_name=hub_client.project
                )
        self._inject_context()
        self.dep_specs = self._dep_specs(hub_client)
        self.cache_specs = self._cache_specs()
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
        parser.add_argument("--cpu", metavar="NUM", type=int)
        parser.add_argument("--memory", metavar="SIZE", type=str)
        parser.add_argument("--gpu", metavar="NUM", type=int)
        parser.add_argument("--gpu-name", metavar="NAME", type=str)
        parser.add_argument("--gpu-memory", metavar="SIZE", type=str)
        parser.add_argument("--shm-size", metavar="SIZE", type=str)
        parser.add_argument(
            "-p", "--port", metavar="PORTS", type=PortMapping, nargs=argparse.ONE_OR_MORE
        )

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
        self.provider_data["ports"] = merge_ports(
            [PortMapping(i) for i in self.provider_data.get("ports") or []], args.port or []
        )
        if unknown_args:
            self.provider_data["run_args"] = unknown_args

    def parse_args(self):
        pass

    def submit_jobs(self, hub_client: "hub.HubClient", tag_name: str) -> List[Job]:
        if not self.loaded:
            raise Exception("The provider is not loaded")
        job_specs = self.create_job_specs()

        with tempfile.NamedTemporaryFile("w+b") as f:
            repo_code_filename = hub_client.repo.repo_data.write_code_file(f)
            f.seek(0)
            # FIXME: this should be replaced with public API call
            hub_client._storage.upload_file(f.name, repo_code_filename, lambda _: ...)

        # [TODO] Handle master job
        jobs = []
        for i, job_spec in enumerate(job_specs):
            job = Job(
                job_id=f"{self.run_name},{self.workflow_name or ''},{i}",
                repo_ref=hub_client.repo.repo_ref,
                hub_user_name="",  # HUB will fill it later
                repo_data=hub_client.repo.repo_data,
                run_name=self.run_name,
                workflow_name=self.workflow_name or None,
                provider_name=self.provider_name,
                status=JobStatus.SUBMITTED,
                submitted_at=get_milliseconds_since_epoch(),
                image_name=job_spec.image_name,
                registry_auth=job_spec.registry_auth,
                commands=job_spec.commands,
                entrypoint=job_spec.entrypoint,
                env=job_spec.env,
                home_dir=self.home_dir,
                working_dir=job_spec.working_dir,
                artifact_specs=job_spec.artifact_specs,
                cache_specs=self.cache_specs,
                host_name=None,
                requirements=job_spec.requirements,
                dep_specs=self.dep_specs,
                master_job=job_spec.master_job,
                app_specs=job_spec.app_specs,
                runner_id=None,
                request_id=None,
                tag_name=tag_name,
                ssh_key_pub=self.ssh_key_pub,
                repo_code_filename=repo_code_filename,
            )
            hub_client.submit_job(job)
            jobs.append(job)
        if tag_name:
            hub_client.add_tag_from_run(tag_name, self.run_name, jobs)
        return jobs

    def _dep_specs(self, hub_client: "hub.HubClient") -> Optional[List[DepSpec]]:
        if self.provider_data.get("deps"):
            return [self._parse_dep_spec(dep, hub_client) for dep in self.provider_data["deps"]]
        else:
            return None

    def _validate_local_path(self, path: str) -> str:
        if path == "~" or path.startswith("~/"):
            if not self.home_dir:
                raise KeyError("home_dir is not defined, local path can't start with ~")
            home = self.home_dir.rstrip("/")
            path = home if path == "~" else f"{home}/{path[len('~/'):]}"
        while path.startswith("./"):
            path = path[len("./") :]
        if not path.startswith("/"):
            pass  # todo: use self.working_dir
        return path

    def _artifact_specs(self) -> Optional[List[ArtifactSpec]]:
        artifact_specs = []
        for item in self.provider_data.get("artifacts", []):
            if isinstance(item, str):
                item = {"artifact_path": item}
            else:
                item["artifact_path"] = item.pop("path")
            item["artifact_path"] = self._validate_local_path(item["artifact_path"])
            artifact_specs.append(ArtifactSpec(**item))
        return artifact_specs or None

    def _cache_specs(self) -> List[CacheSpec]:
        cache_specs = []
        for item in self.provider_data.get("cache", []):
            if isinstance(item, str):
                item = {"path": item}
            item["path"] = self._validate_local_path(item["path"])
            cache_specs.append(CacheSpec(**item))
        return cache_specs

    @staticmethod
    def _parse_dep_spec(dep: Union[dict, str], hub_client) -> DepSpec:
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
                return Provider._tag_dep(hub_client, t[0], mount)
            else:
                return Provider._workflow_dep(hub_client, t[0], mount)
        elif len(t) == 3:
            # This doesn't allow to refer to projects from other repos
            if tag_dep:
                return Provider._tag_dep(hub_client, t[2], mount)
            else:
                return Provider._workflow_dep(hub_client, t[2], mount)
        else:
            sys.exit(f"Invalid dep format: {dep}")

    @staticmethod
    def _tag_dep(hub_client: "hub.HubClient", tag_name: str, mount: bool) -> DepSpec:
        tag_head = hub_client.get_tag_head(tag_name)
        if tag_head:
            return DepSpec(
                repo_ref=hub_client.repo.repo_ref, run_name=tag_head.run_name, mount=mount
            )
        else:
            sys.exit(f"Cannot find the tag '{tag_name}' in the '{hub_client.repo.repo_id}' repo")

    @staticmethod
    def _workflow_dep(hub_client: "hub.HubClient", workflow_name: str, mount: bool) -> DepSpec:
        job_heads = sorted(
            hub_client.list_job_heads(),
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
            return DepSpec(repo_ref=hub_client.repo.repo_ref, run_name=run_name, mount=mount)
        else:
            sys.exit(
                f"Cannot find any successful workflow with the name '{workflow_name}' "
                f"in the '{hub_client.repo.repo_id}' repo"
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

    def _get_entrypoint(self) -> Optional[List[str]]:
        v = self.provider_data.get("entrypoint")
        if isinstance(v, str):
            return shlex.split(v)
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
                gpu_memory = None
                if str(gpu.get("count")).isnumeric():
                    gpu_count = int(gpu.get("count"))
                if gpu.get("name"):
                    gpu_name = gpu.get("name")
                    if not gpu_count:
                        gpu_count = 1
                if gpu.get("memory"):
                    gpu_memory = _str_to_mib(gpu.get("memory"))
                    if not gpu_count:
                        gpu_count = 1
                if gpu_count:
                    resources.gpus = GpusRequirements(
                        count=gpu_count, name=gpu_name, memory_mib=gpu_memory
                    )
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
