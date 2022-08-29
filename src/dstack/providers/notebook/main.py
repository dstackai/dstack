import uuid
from argparse import ArgumentParser
from typing import List, Optional, Dict, Any

from dstack.jobs import AppSpec, JobSpec
from dstack.providers import Provider


class NotebookProvider(Provider):
    def __init__(self):
        super().__init__("notebook")
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
        self.version = self.provider_data.get("version")
        self.requirements = self.provider_data.get("requirements")
        self.env = self._env()
        self.artifact_specs = self._artifact_specs()
        self.working_dir = self.provider_data.get("working_dir")
        self.resources = self._resources()
        self.image_name = self._image()

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
        token = uuid.uuid4().hex
        env["TOKEN"] = token
        return [JobSpec(
            image_name=self.image_name,
            commands=self._commands(),
            env=env,
            working_dir=self.working_dir,
            requirements=self.resources,
            artifact_specs=self.artifact_specs,
            port_count=1,
            app_specs=[AppSpec(
                port_index=0,
                app_name="notebook",
                url_query_params={
                    "token": token
                }
            )]
        )]

    def _image(self) -> str:
        cuda_is_required = self.resources and self.resources.gpu
        return f"dstackai/miniconda:{self.python}-cuda-11.1" if cuda_is_required else f"dstackai/miniconda:{self.python}"

    def _commands(self):
        commands = [
            "pip install jupyter" + (f"=={self.version}" if self.version else ""),
            "mkdir -p /root/.jupyter",
            "echo \"c.NotebookApp.allow_root = True\" > /root/.jupyter/jupyter_notebook_config.py",
            "echo \"c.NotebookApp.open_browser = False\" >> /root/.jupyter/jupyter_notebook_config.py",
            "echo \"c.NotebookApp.port = $JOB_PORT_0\" >> /root/.jupyter/jupyter_notebook_config.py",
            "echo \"c.NotebookApp.token = '$TOKEN'\" >> /root/.jupyter/jupyter_notebook_config.py",
            "echo \"c.NotebookApp.ip = '$JOB_HOSTNAME'\" >> /root/.jupyter/jupyter_notebook_config.py",
        ]
        if self.requirements:
            commands.append("pip install -r " + self.requirements)
        if self.before_run:
            commands.extend(self.before_run)
        commands.append(
            f"jupyter notebook"
        )
        return commands


def __provider__():
    return NotebookProvider()
