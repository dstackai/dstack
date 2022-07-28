from typing import List, Optional
from argparse import ArgumentParser
import argparse

from dstack import Provider, Job, Resources, Gpu


class TorchrunProvider(Provider):
    def __init__(self):
        super().__init__()
        self.script = None
        self.before_run = None
        self.version = None
        self.requirements = None
        self.environment = None
        self.artifacts = None
        self.working_dir = None
        self.nodes = None
        self.resources = None
        self.args = None

    def load(self):
        super()._load(schema="schema.yaml")
        self.script = self.workflow.data.get("script") or self.workflow.data.get("file")
        self.before_run = self.workflow.data.get("before_run")
        self.version = str(self.workflow.data.get("version") or "3.9")
        self.requirements = self.workflow.data.get("requirements")
        self.environment = self.workflow.data.get("environment") or {}
        self.artifacts = self.workflow.data.get("artifacts")
        self.working_dir = self.workflow.data.get("working_dir")
        self.nodes = self.workflow.data.get("nodes") or 1
        self.resources = self._resources()
        self.args = self.workflow.data.get("args")

    def _resources(self) -> Optional[Resources]:
        resources = super()._resources()
        if resources.gpu is None:
            resources.gpu = Gpu(1)
        return resources

    def _image(self):
        return f"dstackai/python:{self.version}-cuda-11.1"

    def _commands(self, node_rank):
        commands = []
        if self.requirements:
            commands.append("pip3 install -r " + self.requirements)
        if self.before_run:
            commands.extend(self.before_run)
        nproc = ""
        if self.resources.gpu:
            nproc = f"--nproc_per_node={self.resources.gpu.count}"
        args_init = ""
        if self.args:
            if isinstance(self.args, str):
                args_init += " " + self.args
            if isinstance(self.args, list):
                args_init += " " + ",".join(map(lambda arg: "\"" + arg.replace('"', '\\"') + "\"", self.args))
        torchrun_command = f"torchrun {nproc} --nnodes={self.nodes} --node_rank={node_rank}"
        if node_rank == 0:
            commands.append(
                f"{torchrun_command} --master_addr $JOB_HOSTNAME --master_port $JOB_PORT_0 {self.script} {args_init}"
            )
        else:
            commands.append(
                f"{torchrun_command} --master_addr $MASTER_JOB_HOSTNAME --master_port $MASTER_JOB_PORT_0 {self.script} {args_init}"
            )
        return commands

    def create_jobs(self) -> List[Job]:
        master_job = Job(
            image=self._image(),
            commands=self._commands(0),
            working_dir=self.working_dir,
            resources=self.resources,
            artifacts=self.artifacts,
            environment=self.environment,
            port_count=1,
        )
        jobs = [master_job]
        if self.nodes > 1:
            for i in range(self.nodes - 1):
                jobs.append(Job(
                    image=self._image(),
                    commands=self._commands(i+1),
                    working_dir=self.working_dir,
                    resources=self.resources,
                    environment=self.environment,
                    master=master_job
                ))
        return jobs

    def _create_parser(self, workflow_name: Optional[str]) -> Optional[ArgumentParser]:
        parser = ArgumentParser(prog="dstack run " + (workflow_name or "torchrun"))
        self._add_base_args(parser)
        parser.add_argument("--nnodes", type=int, nargs="?")
        if not workflow_name:
            parser.add_argument("file", metavar="FILE", type=str)
            parser.add_argument("args", metavar="ARGS", nargs=argparse.ZERO_OR_MORE)
        return parser

    def parse_args(self):
        parser = self._create_parser(self.workflow_name)
        args, unknown = parser.parse_known_args(self.provider_args)
        self._parse_base_args(args)
        if args.nnodes:
            self.workflow.data["nodes"] = args.nnodes
        if self.run_as_provider:
            self.workflow.data["file"] = args.file
            _args = args.args + unknown
            if _args:
                self.workflow.data["args"] = _args


def __provider__():
    return TorchrunProvider()


if __name__ == '__main__':
    __provider__().run()

