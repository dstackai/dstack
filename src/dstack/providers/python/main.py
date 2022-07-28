import argparse
from argparse import ArgumentParser
from typing import List, Optional

from dstack import Provider, Job


# TODO: Make environment a list of VAR=VAL
class PythonProvider(Provider):
    def __init__(self):
        super().__init__()
        self.file = None
        self.before_run = None
        # TODO: Handle numbers such as 3.1 (e.g. require to use strings)
        self.version = None
        self.args = None
        self.requirements = None
        self.environment = None
        self.artifacts = None
        self.working_dir = None
        self.resources = None
        self.image = None

    def load(self):
        super()._load(schema="schema.yaml")
        # Drop the deprecated `script` property, and make `file` required in the schema
        self.file = self.workflow.data.get("script") or self.workflow.data["file"]
        self.before_run = self.workflow.data.get("before_run")
        # TODO: Handle numbers such as 3.1 (e.g. require to use strings)
        self.version = self._save_python_version("version")
        self.args = self.workflow.data.get("args")
        self.requirements = self.workflow.data.get("requirements")
        self.environment = self.workflow.data.get("environment") or {}
        self.artifacts = self.workflow.data.get("artifacts")
        self.working_dir = self.workflow.data.get("working_dir")
        self.resources = self._resources()
        self.image = self._image()

    def _create_parser(self, workflow_name: Optional[str]) -> Optional[ArgumentParser]:
        parser = ArgumentParser(prog="dstack run " + (workflow_name or "python"))
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
            self.workflow.data["file"] = args.file
            _args = args.args + unknown_args
            if _args:
                self.workflow.data["args"] = _args

    def create_jobs(self) -> List[Job]:
        return [Job(
            image=self.image,
            commands=self._commands(),
            environment=self.environment,
            working_dir=self.working_dir,
            resources=self.resources,
            artifacts=self.artifacts
        )]

    def _image(self) -> str:
        cuda_is_required = self.resources and self.resources.gpu
        return f"dstackai/python:{self.version}-cuda-11.1" if cuda_is_required else f"python:{self.version}"

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


if __name__ == '__main__':
    __provider__().run()
