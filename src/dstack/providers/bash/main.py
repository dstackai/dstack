from argparse import ArgumentParser
from typing import List, Optional

from dstack import Provider, Job, App


# TODO: Make environment a list of VAR=VAL
class BashProvider(Provider):
    def __init__(self):
        super().__init__()
        self.file = None
        self.before_run = None
        # TODO: Handle numbers such as 3.1 (e.g. require to use strings)
        self.python = None
        self.requirements = None
        self.environment = None
        self.artifacts = None
        self.working_dir = None
        self.resources = None
        self.ports = None

    def load(self):
        super()._load(schema="schema.yaml")
        self.before_run = self.workflow.data.get("before_run")
        self.python = self._save_python_version("python")
        self.commands = self.workflow.data.get("commands")
        self.requirements = self.workflow.data.get("requirements")
        self.environment = self.workflow.data.get("environment") or {}
        self.artifacts = self.workflow.data.get("artifacts")
        self.working_dir = self.workflow.data.get("working_dir")
        self.ports = self.workflow.data.get("ports")
        self.resources = self._resources()
        self.image = self._image()

    def _create_parser(self, workflow_name: Optional[str]) -> Optional[ArgumentParser]:
        parser = ArgumentParser(prog="dstack run " + (workflow_name or "bash"))
        self._add_base_args(parser)
        parser.add_argument("-p", "--ports", metavar="PORT_COUNT", type=int)
        if not workflow_name:
            parser.add_argument("-c", "--command", type=str)
        return parser

    def parse_args(self):
        parser = self._create_parser(self.workflow_name)
        args = parser.parse_args(self.provider_args)
        self._parse_base_args(args)
        if self.run_as_provider:
            self.workflow.data["commands"] = [args.command]
        if args.ports:
            self.workflow.data["ports"] = args.ports

    def create_jobs(self) -> List[Job]:
        apps = None
        if self.ports:
            apps = []
            for i in range(self.ports):
                apps.append(
                    App(
                        port_index=i,
                        app_name="bash" + (i if self.ports > 1 else ""),
                    )
                )
        return [Job(
            image=self.image,
            commands=self._commands(),
            environment=self.environment,
            working_dir=self.working_dir,
            resources=self.resources,
            artifacts=self.artifacts,
            port_count=self.ports,
            apps=apps
        )]

    def _image(self) -> str:
        cuda_is_required = self.resources and self.resources.gpu
        return f"dstackai/python:{self.python}-cuda-11.1" if cuda_is_required else f"python:{self.python}"

    def _commands(self):
        commands = []
        if self.requirements:
            commands.append("pip install -r " + self.requirements)
        if self.before_run:
            commands.extend(self.before_run)
        commands.extend(self.commands)
        return commands


def __provider__():
    return BashProvider()


if __name__ == '__main__':
    __provider__().run()
