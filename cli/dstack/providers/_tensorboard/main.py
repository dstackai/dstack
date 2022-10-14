from argparse import ArgumentParser
from typing import List, Optional, Dict, Any

from dstack.backend import load_backend
from dstack.config import load_config
from dstack.jobs import JobSpec, JobHead, AppSpec
from dstack.providers import Provider


class TensorboardProvider(Provider):
    def __init__(self):
        super().__init__("tensorboard")
        self.app = None
        self.before_run = None
        self.python = None
        self.version = None
        self.run_names = None
        self.logdir = None

    def load(self, provider_args: List[str], workflow_name: Optional[str], provider_data: Dict[str, Any]):
        super().load(provider_args, workflow_name, provider_data)
        self.before_run = self.provider_data.get("before_run")
        self.python = self._safe_python_version("python")
        self.version = self.provider_data.get("version")
        self.run_names = self.provider_data["runs"]
        self.logdir = self.provider_data.get("logdir")

    def _create_parser(self, workflow_name: Optional[str]) -> Optional[ArgumentParser]:
        parser = ArgumentParser(prog="dstack run " + (workflow_name or self.provider_name))
        if not workflow_name:
            parser.add_argument("run_names", metavar="RUN", type=str, nargs="+", help="A name of a run")
            parser.add_argument("--logdir", type=str, help="The path where TensorBoard will look for "
                                                           "event files. By default, TensorBoard will"
                                                           "scan all run artifacts.")
        return parser

    def parse_args(self):
        parser = self._create_parser(self.workflow_name)
        args = parser.parse_args(self.provider_args)
        if self.run_as_provider:
            self.provider_data["runs"] = args.run_names
            if args.logdir:
                self.provider_data["logdir"] = args.logdir

    def create_job_specs(self) -> List[JobSpec]:
        return [JobSpec(
            image_name="python:3.10",
            commands=self._commands(),
            port_count=1,
            app_specs=[AppSpec(
                port_index=0,
                app_name="tensorboard",
            )]
        )]

    def __get_job_heads_by_run_name(self, run_names: Dict[str, List[JobHead]]):
        backend = load_backend()
        job_heads_by_run_name = {}
        for run_name in run_names:
            job_heads = backend.list_job_heads(self.provider_data["repo_user_name"], self.provider_data["repo_name"],
                                               run_name)
            job_heads_by_run_name[run_name] = job_heads
        return job_heads_by_run_name

    def _commands(self):
        commands = [
            "pip install boto3",
            "pip install tensorboard" + (f"=={self.version}" if self.version else ""),
        ]
        if self.before_run:
            commands.extend(self.before_run)

        logdir = []
        config = load_config()
        job_heads_by_run_name = self.__get_job_heads_by_run_name(self.run_names)
        repo_user_name = self.provider_data["repo_user_name"]
        repo_name = self.provider_data["repo_name"]

        for run_name in job_heads_by_run_name:
            job_heads = job_heads_by_run_name[run_name]
            for job_head in job_heads:
                ld = f"s3://{config.backend_config.bucket_name}/artifacts/{repo_user_name}/{repo_name}/" \
                     f"{job_head.job_id}"
                if self.logdir:
                    ld += "/" + self.logdir
                logdir.append(ld)

        commands.append(f"tensorboard --port $PORT_0 --host 0.0.0.0 --logdir {','.join(logdir)}")
        return commands


def __provider__():
    return TensorboardProvider()
