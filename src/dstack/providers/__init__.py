import importlib
import sys
import time
from abc import abstractmethod
from argparse import ArgumentParser, Namespace
from pkgutil import iter_modules
from typing import Optional, List, Dict, Any

from dstack.backend import load_backend
from dstack.jobs import Job, JobStatus, JobSpec, JobRef, Requirements, GpusRequirements
from dstack.repo import load_repo
from dstack.util import _quoted


def _str_to_mib(s: str) -> int:
    ns = s.replace(" ", "").lower()
    if ns.endswith('mib'):
        return int(s[:-3])
    elif ns.endswith('gib'):
        return int(s[:-3]) * 1024
    elif ns.endswith('mi'):
        return int(s[:-2])
    elif ns.endswith('gi'):
        return int(s[:-2]) * 1024
    elif ns.endswith('mb'):
        return int(int(s[:-2]) * 1000 * 1000 / 1024 / 1024)
    elif ns.endswith('gb'):
        return int(int(s[:-2]) * (1000 * 1000 * 1000) / 1024 / 1024)
    elif ns.endswith('m'):
        return int(int(s[:-1]) * 1000 * 1000 / 1024 / 1024)
    elif ns.endswith('g'):
        return int(int(s[:-1]) * (1000 * 1000 * 1000) / 1024 / 1024)
    else:
        raise Exception(f"Unknown memory unit: {s}")


class Provider:
    def __init__(self, provider_name: str):
        self.provider_name = provider_name
        self.provider_data = None
        self.provider_args = None
        self.workflow_name = None
        self.run_as_provider = None
        self.loaded = False

    def __str__(self) -> str:
        return f'Provider(name="{self.provider_name}", ' \
               f'workflow_data="{self.provider_data}", ' \
               f'workflow_name="{_quoted(self.workflow_name)}, ' \
               f'provider_name="{self.provider_name}", ' \
               f'run_as_provider={self.run_as_provider})'

    # TODO: This is a dirty hack
    def _save_python_version(self, name: str):
        v = self.provider_data.get(name)
        if isinstance(v, str):
            return v
        elif v == 3.1:
            return "3.10"
        elif v:
            return str(v)
        else:
            return "3.10"

    def load(self, provider_args: List[str], workflow_name: Optional[str], provider_data: Dict[str, Any]):
        self.provider_args = provider_args
        self.workflow_name = workflow_name
        self.provider_data = provider_data
        self.run_as_provider = not workflow_name
        self.parse_args()
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
        parser.add_argument("-r", "--requirements", type=str)
        parser.add_argument("-e", "--env", action='append')
        parser.add_argument("-a", "--artifact", metavar="ARTIFACT", dest="artifacts", action='append')
        # parser.add_argument("-d", "--dep", metavar="TAG | WORKFLOW", dest="deps", action='append')
        parser.add_argument("-w", "--working-dir", type=str)
        parser.add_argument("-i", "--interruptible", action="store_true")
        parser.add_argument("--cpu", type=int)
        parser.add_argument("--memory", type=str)
        parser.add_argument("--gpu", type=int)
        parser.add_argument("--gpu-name", type=str)
        parser.add_argument("--gpu-memory", type=str)
        parser.add_argument("--shm-size", type=str)

    def _parse_base_args(self, args: Namespace):
        if args.requirements:
            self.provider_data["requirements"] = args.requirements
        if args.artifacts:
            self.provider_data["artifacts"] = args.artifacts
        # if args.deps:
        #     self.provider_data["deps"] = args.deps
        if args.working_dir:
            self.provider_data["working_dir"] = args.working_dir
        if args.env:
            environment = self.provider_data.get("environment") or {}
            for e in args.env:
                if "=" in e:
                    tokens = e.split("=", maxsplit=1)
                    environment[tokens[0]] = tokens[1]
                else:
                    environment[e] = ""
            self.provider_data["environment"] = environment
        if args.cpu or args.memory or args.gpu or args.gpu_name or args.gpu_memory or args.shm_size or args.interruptible:
            resources = self.provider_data.get("resources") or {}
            self.provider_data["resources"] = resources
            if args.cpu:
                resources["cpu"] = args.cpu
            if args.memory:
                resources["memory"] = args.memory
            if args.gpu or args.gpu_name or args.gpu_memory:
                gpu = self.provider_data["resources"].get("gpu") or {} if self.provider_data.get("resources") else {}
                if type(gpu) is int:
                    gpu = {
                        "count": gpu
                    }
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

    def parse_args(self):
        pass

    def submit_jobs(self, run_name: Optional[str] = None) -> List[Job]:
        if not self.loaded:
            raise Exception("The provider is not loaded")
        job_specs = self.create_job_specs()
        repo = load_repo()
        backend = load_backend()
        # [TODO] Handle previous jobs and master job
        jobs = []
        counter = []
        for job_spec in job_specs:
            previous_jobs = []
            if self.provider_data.get("previous_job_ids"):
                for jid in self.provider_data.get("previous_job_ids"):
                    previous_jobs.append(JobRef(str(jid)))
            if job_spec.previous_jobs:
                previous_jobs.extend(job_spec.previous_jobs)
            submitted_at = int(round(time.time() * 1000))
            job = Job(repo, run_name or self.provider_data["run_name"], self.provider_data.get("workflow_name") or None,
                      self.provider_data.get("provider_name") or None, JobStatus.SUBMITTED, submitted_at,
                      job_spec.image_name, job_spec.commands, job_spec.env,
                      job_spec.working_dir, job_spec.artifacts, job_spec.port_count, None, None,
                      job_spec.requirements, previous_jobs, job_spec.master_job, job_spec.apps, None, None)
            backend.submit_job(job, counter)
            jobs.append(job)
        return jobs

    def _resources(self) -> Optional[Requirements]:
        if self.provider_data.get("resources"):
            resources = Requirements()
            if self.provider_data["resources"].get("cpu"):
                if not str(self.provider_data["resources"]["cpu"]).isnumeric():
                    sys.exit("resources.cpu in workflows.yaml should be an integer")
                cpu = int(self.provider_data["resources"]["cpu"])
                if cpu > 0:
                    resources.cpus = cpu
            if self.provider_data["resources"].get("memory"):
                resources.memory_mib = _str_to_mib(self.provider_data["resources"]["memory"])
            gpu = self.provider_data["resources"].get("gpu")
            if gpu:
                if str(gpu).isnumeric():
                    gpu = int(self.provider_data["resources"]["gpu"])
                    if gpu > 0:
                        resources.gpus = GpusRequirements(gpu)
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
                        resources.gpus = GpusRequirements(gpu_count, name=gpu_name)
            for resource_name in self.provider_data["resources"]:
                if resource_name.endswith("/gpu") and len(resource_name) > 4:
                    if not str(self.provider_data["resources"][resource_name]).isnumeric():
                        sys.exit(f"resources.'{resource_name}' in workflows.yaml should be an integer")
                    gpu = int(self.provider_data["resources"][resource_name])
                    if gpu > 0:
                        resources.gpus = GpusRequirements(gpu, name=resource_name[:-4])
            if self.provider_data["resources"].get("shm_size"):
                resources.shm_size = self.provider_data["resources"]["shm_size"]
            if self.provider_data["resources"].get("interruptible"):
                resources.interruptible = self.provider_data["resources"]["interruptible"]
            if resources.cpus or resources.memory_mib or resources.gpus or resources.shm_size or resources.interruptible:
                return resources
            else:
                return None


def get_providers_names() -> List[str]:
    return list(map(lambda m: m[1], filter(lambda m: m.ispkg, iter_modules(sys.modules[__name__].__path__))))


def load_provider(provider_name) -> Provider:
    return importlib.import_module(f"dstack.providers.{provider_name}.main").__provider__()
