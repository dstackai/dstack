import argparse
from argparse import ArgumentParser
from typing import Any, Dict, List, Optional

from rich_argparse import RichHelpFormatter

from dstack.backend.base import Backend
from dstack.core.job import GpusRequirements, JobSpec, Requirements
from dstack.providers import Provider


class TorchrunProvider(Provider):
    def __init__(self):
        super().__init__("torchrun")
        self.script = None
        self.setup = None
        self.python = None
        self.env = None
        self.artifact_specs = None
        self.working_dir = None
        self.nodes = None
        self.resources = None
        self.args = None

    def load(
        self,
        backend: Backend,
        provider_args: List[str],
        workflow_name: Optional[str],
        provider_data: Dict[str, Any],
        run_name: str,
    ):
        super().load(backend, provider_args, workflow_name, provider_data, run_name)
        self.script = self.provider_data.get("script") or self.provider_data.get("file")
        self.setup = self._get_list_data("setup") or self._get_list_data("before_run")
        self.python = self._safe_python_version("python")
        self.env = self._env()
        self.artifact_specs = self._artifact_specs()
        self.working_dir = self.provider_data.get("working_dir")
        self.nodes = self.provider_data.get("nodes") or 1
        self.resources = self._resources()
        self.args = self.provider_data.get("args")

    def _resources(self) -> Optional[Requirements]:
        resources = super()._resources()
        if resources.gpu is None:
            resources.gpu = GpusRequirements(count=1)
        return resources

    def _image_name(self) -> str:
        cuda_is_required = self.resources and self.resources.gpus
        cuda_image_name = f"dstackai/miniforge:{self.python}-cuda-11.1"
        cpu_image_name = f"dstackai/miniforge:{self.python}"
        return cuda_image_name if cuda_is_required else cpu_image_name

    def _commands(self, node_rank):
        commands = []
        if self.setup:
            commands.extend(self.setup)
        nproc = ""
        if self.resources.gpu:
            nproc = f"--nproc_per_node={self.resources.gpu.count}"
        args_init = ""
        if self.args:
            if isinstance(self.args, str):
                args_init += " " + self.args
            if isinstance(self.args, list):
                args_init += " " + ",".join(
                    map(lambda arg: '"' + arg.replace('"', '\\"') + '"', self.args)
                )
        torchrun_command = f"torchrun {nproc} --nnodes={self.nodes} --node_rank={node_rank}"
        if node_rank == 0:
            commands.append(
                f"{torchrun_command} --master_addr $JOB_HOSTNAME --master_port $JOB_PORT_0 {self.script} {args_init}"
            )
        else:
            commands.append(
                f"{torchrun_command} --master_addr $MASTER_JOB_HOSTNAME --master_port $MASTER_JOB_PORT_0 "
                f"{self.script} {args_init}"
            )
        return commands

    def create_job_specs(self) -> List[JobSpec]:
        master_job = JobSpec(
            image_name=self._image_name(),
            commands=self._commands(0),
            env=self.env,
            working_dir=self.working_dir,
            artifact_specs=self.artifact_specs,
            requirements=self.resources,
            port_count=1,
        )
        job_specs = [master_job]
        if self.nodes > 1:
            for i in range(self.nodes - 1):
                job_specs.append(
                    JobSpec(
                        image_name=self._image_name(),
                        commands=self._commands(i + 1),
                        working_dir=self.working_dir,
                        env=self.env,
                        requirements=self.resources,
                        master_job=master_job,
                    )
                )
        return job_specs

    def _create_parser(self, workflow_name: Optional[str]) -> Optional[ArgumentParser]:
        parser = ArgumentParser(
            prog="dstack run " + (workflow_name or self.provider_name),
            formatter_class=RichHelpFormatter,
        )
        self._add_base_args(parser)
        parser.add_argument("--nnodes", type=int, nargs="?")
        if not workflow_name:
            parser.add_argument("file", metavar="FILE", type=str)
            parser.add_argument("args", metavar="ARGS", nargs=argparse.ZERO_OR_MORE)
        return parser

    def parse_args(self):
        parser = self._create_parser(self.workflow_name)
        args, unknown_args = parser.parse_known_args(self.provider_args)
        self._parse_base_args(args, unknown_args)
        if args.nnodes:
            self.provider_data["nodes"] = args.nnodes
        if self.run_as_provider:
            self.provider_data["file"] = args.file
            _args = args.args + unknown_args
            if _args:
                self.provider_data["args"] = _args


def __provider__():
    return TorchrunProvider()
