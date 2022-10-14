import uuid
from argparse import ArgumentParser
from typing import List, Optional, Dict, Any

from dstack.jobs import JobSpec, AppSpec
from dstack.providers import Provider


class CodeProvider(Provider):
    def __init__(self):
        super().__init__("code")
        self.before_run = None
        self.python = None
        self.version = None
        self.requirements = None
        self.env = None
        self.artifact_specs = None
        self.working_dir = None
        self.resources = None
        self.image_name = None

    def load(self, provider_args: List[str], workflow_name: Optional[str], provider_data: Dict[str, Any]):
        super().load(provider_args, workflow_name, provider_data)
        self.before_run = self.provider_data.get("before_run")
        self.python = self._safe_python_version("python")
        self.version = self.provider_data.get("version") or "1.71.0"
        self.requirements = self.provider_data.get("requirements")
        self.env = self._env()
        self.artifact_specs = self._artifact_specs()
        self.working_dir = self.provider_data.get("working_dir")
        self.resources = self._resources()
        self.image_name = self._image_name()

    def _create_parser(self, workflow_name: Optional[str]) -> Optional[ArgumentParser]:
        parser = ArgumentParser(prog="dstack run " + (workflow_name or self.provider_name))
        self._add_base_args(parser)
        return parser

    def parse_args(self):
        parser = self._create_parser(self.workflow_name)
        args = parser.parse_args(self.provider_args)
        self._parse_base_args(args)

    def create_job_specs(self) -> List[JobSpec]:
        env = dict(self.env or {})
        connection_token = uuid.uuid4().hex
        env["CONNECTION_TOKEN"] = connection_token
        return [JobSpec(
            image_name=self.image_name,
            commands=self._commands(),
            env=env,
            working_dir=self.working_dir,
            artifact_specs=self.artifact_specs,
            port_count=1,
            requirements=self.resources,
            app_specs=[AppSpec(
                port_index=0,
                app_name="code",
                url_query_params={
                    "tkn": connection_token,
                    "folder": "/workflow"
                }
            )]
        )]

    def _image_name(self) -> str:
        cuda_is_required = self.resources and self.resources.gpus
        cuda_image_name = f"dstackai/miniconda:{self.python}-cuda-11.1"
        cpu_image_name = f"dstackai/miniconda:{self.python}"
        return cuda_image_name if cuda_is_required else cpu_image_name

    def _commands(self):
        commands = [
            "mkdir -p /tmp",
            "cd /tmp",
            f"wget -q https://github.com/gitpod-io/openvscode-server/releases/download/"
            f"openvscode-server-v{self.version}/openvscode-server-v{self.version}-linux-x64.tar.gz -O "
            f"openvscode-server-v{self.version}-linux-x64.tar.gz",
            f"tar -xzf openvscode-server-v{self.version}-linux-x64.tar.gz",
            f"cd openvscode-server-v{self.version}-linux-x64",
            "./bin/openvscode-server --install-extension ms-python.python",
            "rm /usr/bin/python2*",
        ]
        if self.requirements:
            commands.append("pip install -r " + self.requirements)
        if self.before_run:
            commands.extend(self.before_run)
        commands.append(
            "./bin/openvscode-server --port $PORT_0 --host 0.0.0.0 --connection-token $CONNECTION_TOKEN"
        )
        return commands


def __provider__():
    return CodeProvider()
