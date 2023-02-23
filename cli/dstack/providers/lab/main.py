import uuid
from argparse import ArgumentParser
from typing import Any, Dict, List, Optional

from dstack.backend.base import Backend
from dstack.core.app import AppSpec
from dstack.core.job import JobSpec
from dstack.providers import Provider


class LabProvider(Provider):
    def __init__(self):
        super().__init__("lab")
        self.setup = None
        self.python = None
        self.version = None
        self.env = None
        self.artifact_specs = None
        self.working_dir = None
        self.resources = None
        self.image_name = None

    def load(
        self,
        backend: Backend,
        provider_args: List[str],
        workflow_name: Optional[str],
        provider_data: Dict[str, Any],
        run_name: str,
    ):
        super().load(backend, provider_args, workflow_name, provider_data, run_name)
        self.setup = self._get_list_data("setup") or self._get_list_data("before_run")
        self.python = self._safe_python_version("python")
        self.version = self.provider_data.get("version")
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
        args, unknown_args = parser.parse_known_args(self.provider_args)
        self._parse_base_args(args, unknown_args)

    def create_job_specs(self) -> List[JobSpec]:
        env = {}
        token = uuid.uuid4().hex
        env["TOKEN"] = token
        return [
            JobSpec(
                image_name=self.image_name,
                commands=self._commands(),
                env=env,
                working_dir=self.working_dir,
                artifact_specs=self.artifact_specs,
                port_count=1,
                requirements=self.resources,
                app_specs=[
                    AppSpec(
                        port_index=0,
                        app_name="lab",
                        url_path="lab",
                        url_query_params={"token": token},
                    )
                ],
            )
        ]

    def _image_name(self) -> str:
        cuda_is_required = self.resources and self.resources.gpus
        cuda_image_name = f"dstackai/miniforge:{self.python}-cuda-11.1"
        cpu_image_name = f"dstackai/miniforge:{self.python}"
        return cuda_image_name if cuda_is_required else cpu_image_name

    def _commands(self):
        commands = []
        if self.env:
            self._extend_commands_with_env(commands, self.env)
        commands.extend(
            [
                "conda install psutil -y",
                "pip install jupyterlab" + (f"=={self.version}" if self.version else ""),
                "pip install ipywidgets",
                "jupyter nbextension enable --py widgetsnbextension",
                "mkdir -p /root/.jupyter",
                'echo "c.ServerApp.allow_root = True" > /root/.jupyter/jupyter_server_config.py',
                "echo \"c.ServerApp.allow_origin = '*'\" >> /root/.jupyter/jupyter_server_config.py",
                'echo "c.ServerApp.open_browser = False" >> /root/.jupyter/jupyter_server_config.py',
                'echo "c.ServerApp.port = $PORT_0" >> /root/.jupyter/jupyter_server_config.py',
                "echo \"c.ServerApp.token = '$TOKEN'\" >> /root/.jupyter/jupyter_server_config.py",
                "echo \"c.ServerApp.ip = '0.0.0.0'\" >> /root/.jupyter/jupyter_server_config.py",
            ]
        )
        if self.setup:
            commands.extend(self.setup)
        commands.append(f"jupyter lab")
        return commands


def __provider__():
    return LabProvider()
