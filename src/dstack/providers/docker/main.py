import argparse
from argparse import ArgumentParser
from typing import List, Optional

from dstack import Provider, Job, App


class DockerProvider(Provider):
    def __init__(self):
        super().__init__()
        self.image = None
        self.before_run = None
        self.commands = None
        self.artifacts = None
        self.environment = None
        self.working_dir = None
        self.ports = None
        self.resources = None

    def load(self):
        super()._load(schema="schema.yaml")
        self.image = self.workflow.data["image"]
        self.before_run = self.workflow.data.get("before_run")
        self.commands = self.workflow.data.get("commands")
        self.artifacts = self.workflow.data.get("artifacts")
        self.environment = self.workflow.data.get("environment")
        self.working_dir = self.workflow.data.get("working_dir")
        self.ports = self.workflow.data.get("ports")
        self.resources = self._resources()

    def _create_parser(self, workflow_name: Optional[str]) -> Optional[ArgumentParser]:
        parser = ArgumentParser(prog="dstack run " + (workflow_name or "docker"))
        self._add_base_args(parser)
        parser.add_argument("-p", "--ports", type=int)
        if not workflow_name:
            parser.add_argument("image", metavar="IMAGE", type=str)
            parser.add_argument("-c", "--command", type=str)
        return parser

    def parse_args(self):
        parser = self._create_parser(self.workflow_name)
        args = parser.parse_args(self.provider_args)
        self._parse_base_args(args)
        if self.run_as_provider:
            self.workflow.data["image"] = args.image
            if args.command:
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
                        app_name="docker" + (i if self.ports > 1 else ""),
                    )
                )
        commands = []
        if self.before_run:
            commands.extend(self.before_run)
        commands.extend(self.commands)
        return [Job(
            image=self.image,
            commands=commands,
            environment=self.environment,
            working_dir=self.working_dir,
            resources=self.resources,
            artifacts=self.artifacts,
            port_count=self.ports,
            apps=apps
        )]


def __provider__():
    return DockerProvider()


if __name__ == '__main__':
    __provider__().run()
