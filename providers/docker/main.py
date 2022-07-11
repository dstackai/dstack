import argparse
from argparse import ArgumentParser
from typing import List

from dstack import Provider, Job


class DockerProvider(Provider):
    def __init__(self):
        super().__init__(schema="providers/docker/schema.yaml")
        self.image = self.workflow.data["image"]
        self.before_run = self.workflow.data.get("before_run")
        self.commands = self.workflow.data.get("commands")
        self.artifacts = self.workflow.data.get("artifacts")
        self.environment = self.workflow.data.get("environment")
        self.working_dir = self.workflow.data.get("working_dir")
        self.ports = self.workflow.data.get("ports")
        self.resources = self._resources()

    def parse_args(self):
        parser = ArgumentParser(prog="dstack run docker")
        self._add_base_args(parser)
        parser.add_argument("--ports", type=int, nargs="?")
        if self.run_as_provider:
            parser.add_argument("image", metavar="IMAGE", type=str)
            parser.add_argument("-c", "--command", nargs="?")
        args = parser.parse_args(self.provider_args)
        self._parse_base_args(args)
        if self.run_as_provider:
            self.workflow.data["image"] = args.image
            if args.command:
                self.workflow.data["commands"] = [args.command]
        if args.ports:
            self.workflow.data["ports"] = args.ports

    def create_jobs(self) -> List[Job]:
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
            port_count=self.ports
        )]


if __name__ == '__main__':
    provider = DockerProvider()
    provider.start()
