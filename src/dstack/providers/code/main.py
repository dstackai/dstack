import uuid
from argparse import ArgumentParser
from typing import List, Optional

from dstack import Provider, Job, App


# TODO: Provide job.applications (incl. application name, and query)
class CodeProvider(Provider):
    def __init__(self):
        super().__init__()
        self.before_run = None
        self.python = None
        self.version = None
        self.requirements = None
        self.environment = None
        self.artifacts = None
        self.working_dir = None
        self.resources = None
        self.image = None

    def load(self):
        super()._load(schema="schema.yaml")
        self.before_run = self.workflow.data.get("before_run")
        # TODO: Handle numbers such as 3.1 (e.g. require to use strings)
        self.python = self._save_python_version("python")
        self.version = self.workflow.data.get("version") or "1.67.2"
        self.requirements = self.workflow.data.get("requirements")
        self.environment = self.workflow.data.get("environment") or {}
        self.artifacts = self.workflow.data.get("artifacts")
        self.working_dir = self.workflow.data.get("working_dir")
        self.resources = self._resources()
        self.image = self._image()

    def _create_parser(self, workflow_name: Optional[str]) -> Optional[ArgumentParser]:
        parser = ArgumentParser(prog="dstack run " + (workflow_name or "code"))
        self._add_base_args(parser)
        return parser

    def parse_args(self):
        parser = self._create_parser(self.workflow_name)
        args = parser.parse_args(self.provider_args)
        self._parse_base_args(args)

    def create_jobs(self) -> List[Job]:
        environment = dict(self.environment)
        connection_token = uuid.uuid4().hex
        environment["CONNECTION_TOKEN"] = connection_token
        return [Job(
            image=self.image,
            commands=self._commands(),
            environment=environment,
            working_dir=self.working_dir,
            resources=self.resources,
            artifacts=self.artifacts,
            port_count=1,
            apps=[App(
                port_index=0,
                app_name="code",
                url_query_params={
                    "tkn": connection_token,
                    "folder": "/workflow"
                }
            )]
        )]

    def _image(self) -> str:
        cuda_is_required = self.resources and self.resources.gpu
        return f"dstackai/python:{self.python}-cuda-11.1" if cuda_is_required else f"python:{self.python}"

    def _commands(self):
        commands = [
            "mkdir -p /tmp",
            "cd /tmp",
            f"curl -L https://github.com/gitpod-io/openvscode-server/releases/download/openvscode-server-v{self.version}/openvscode-server-v{self.version}-linux-x64.tar.gz -O",
            f"tar -xzf openvscode-server-v{self.version}-linux-x64.tar.gz",
            f"cd openvscode-server-v{self.version}-linux-x64",
            "./bin/openvscode-server --install-extension ms-python.python"
        ]
        if self.requirements:
            commands.append("pip install -r " + self.requirements)
        if self.before_run:
            commands.extend(self.before_run)
        commands.append(
            "./bin/openvscode-server --port $JOB_PORT_0 --host --host 0.0.0.0 --connection-token $CONNECTION_TOKEN"
        )
        return commands


def __provider__():
    return CodeProvider()


if __name__ == '__main__':
    __provider__().run()
