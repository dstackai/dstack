import argparse
from argparse import ArgumentParser
from typing import List, Optional, Dict, Any

from dstack.jobs import JobSpec
from dstack.providers import Provider


class PythonProvider(Provider):
    def __init__(self):
        super().__init__("python")
        self.file = None
        self.before_run = None
        # TODO: Handle numbers such as 3.1 (e.g. require to use strings)
        self.version = None
        self.args = None
        self.requirements = None
        self.env = None
        self.artifact_specs = None
        self.working_dir = None
        self.resources = None
        self.image_name = None

    def load(self, provider_args: List[str], workflow_name: Optional[str], provider_data: Dict[str, Any]):
        super().load(provider_args, workflow_name, provider_data)
        self.file = self.provider_data["file"]
        self.before_run = self.provider_data.get("before_run")
        self.version = self._safe_python_version("version")
        self.args = self.provider_data.get("args")
        self.requirements = self.provider_data.get("requirements")
        self.env = self._env()
        self.artifact_specs = self._artifact_specs()
        self.working_dir = self.provider_data.get("working_dir")
        self.resources = self._resources()
        self.image_name = self._image_name()

    def _create_parser(self, workflow_name: Optional[str]) -> Optional[ArgumentParser]:
        parser = ArgumentParser(prog="dstack run " + (workflow_name or self.provider_name))
        self._add_base_args(parser)
        if not workflow_name:
            parser.add_argument("file", metavar="FILE", type=str)
            parser.add_argument("args", metavar="ARGS", nargs=argparse.ZERO_OR_MORE)
        return parser

    def parse_args(self):
        parser = self._create_parser(self.workflow_name)
        args, unknown_args = parser.parse_known_args(self.provider_args)
        self._parse_base_args(args)
        if self.run_as_provider:
            self.provider_data["file"] = args.file
            _args = args.args + unknown_args
            if _args:
                self.provider_data["args"] = _args

    def create_job_specs(self) -> List[JobSpec]:
        return [JobSpec(
            image_name=self.image_name,
            commands=self._commands(),
            env=self.env,
            working_dir=self.working_dir,
            artifact_specs=self.artifact_specs,
            requirements=self.resources,
        )]

    def _image_name(self) -> str:
        cuda_is_required = self.resources and self.resources.gpus
        return f"dstackai/miniconda:{self.version}-cuda-11.1" if cuda_is_required else f"dstackai/miniconda:{self.version}"

    def _commands(self):
        commands = []
        if self.requirements:
            commands.append("pip install -r " + self.requirements)
        if self.before_run:
            commands.extend(self.before_run)
        args_init = ""
        if self.args:
            if isinstance(self.args, str):
                args_init += " " + self.args
            if isinstance(self.args, list):
                args_init += " " + ",".join(map(lambda arg: "\"" + arg.replace('"', '\\"') + "\"", self.args))
        commands.append(
            f"python {self.file}{args_init}"
        )
        return commands


def __provider__():
    return PythonProvider()
