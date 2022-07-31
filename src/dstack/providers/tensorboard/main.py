import os
from argparse import ArgumentParser
from typing import List, Optional, Dict

from dstack import App, JobSpec, Job, JobHead
from dstack.backend import get_backend
from dstack.cli.common import get_jobs
from dstack.config import load_config
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

    def load(self):
        super()._load(schema="schema.yaml")
        self.before_run = self.workflow.data.get("before_run")
        # TODO: Handle numbers such as 3.1 (e.g. require to use strings)
        self.python = self._save_python_version("python")
        self.version = self.workflow.data.get("version")
        self.run_names = self.workflow.data["runs"]
        self.logdir = self.workflow.data.get("logdir")

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
            self.workflow.data["runs"] = args.run_names
            if args.logdir:
                self.workflow.data["logdir"] = args.logdir

    def create_job_specs(self) -> List[JobSpec]:
        return [JobSpec(
            image_name="python:3.10",
            commands=self._commands(),
            port_count=1,
            apps=[App(
                port_index=0,
                app_name="tensorboard",
            )]
        )]

    def __get_job_heads_by_run_name(self, run_names: Dict[str, List[JobHead]]):
        backend = get_backend()
        job_heads_by_run_name = {}
        for run_name in run_names:
            job_heads = backend.get_job_heads(self.workflow.data["repo_user_name"], self.workflow.data["repo_name"],
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
        repo_user_name = self.workflow.data["repo_user_name"]
        repo_name = self.workflow.data["repo_name"]

        for run_name in job_heads_by_run_name:
            job_heads = job_heads_by_run_name[run_name]
            for job_head in job_heads:
                ld = f"s3://{config.backend.bucket}/artifacts/{repo_user_name}/{repo_name}/{job_head.get_id()}"
                if self.logdir:
                    ld += "/" + self.logdir
                logdir.append(ld)

        commands.append(f"tensorboard --port $PORT_0 --host 0.0.0.0 --logdir {','.join(logdir)}")
        return commands


def __provider__():
    return TensorboardProvider()


if __name__ == '__main__':
    __provider__().submit_jobs()
