import uuid
from argparse import ArgumentParser, Namespace
from typing import Any, Dict, List, Optional

from rich_argparse import RichHelpFormatter

import dstack.api.hub as hub
from dstack import version
from dstack.core.app import AppSpec
from dstack.core.job import JobSpec
from dstack.providers import Provider
from dstack.providers.extensions import OpenSSHExtension
from dstack.providers.ports import filter_reserved_ports, get_map_to_port


class LabProvider(Provider):
    lab_port = 10000

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
        self.home_dir = "/root"

    def load(
        self,
        hub_client: "hub.HubClient",
        args: Optional[Namespace],
        workflow_name: Optional[str],
        provider_data: Dict[str, Any],
        run_name: str,
        ssh_key_pub: Optional[str] = None,
    ):
        super().load(hub_client, args, workflow_name, provider_data, run_name, ssh_key_pub)
        self.setup = self._get_list_data("setup") or self._get_list_data("before_run")
        self.python = self._safe_python_version("python")
        self.version = self.provider_data.get("version")
        self.env = self._env()
        self.artifact_specs = self._artifact_specs()
        self.working_dir = self.provider_data.get("working_dir")
        self.resources = self._resources()
        self.image_name = self._image_name()

    def _create_parser(self, workflow_name: Optional[str]) -> Optional[ArgumentParser]:
        parser = ArgumentParser(
            prog="dstack run " + (workflow_name or self.provider_name),
            formatter_class=RichHelpFormatter,
        )
        self._add_base_args(parser)
        parser.add_argument("--ssh", action="store_true", dest="openssh_server")
        return parser

    def parse_args(self):
        parser = self._create_parser(self.workflow_name)
        args, unknown_args = parser.parse_known_args(self.provider_args)
        self._parse_base_args(args, unknown_args)
        if args.openssh_server:
            self.openssh_server = True

    def create_job_specs(self) -> List[JobSpec]:
        env = {}
        token = uuid.uuid4().hex
        env["TOKEN"] = token
        apps = []
        for i, pm in enumerate(filter_reserved_ports(self.ports), start=1):
            apps.append(
                AppSpec(
                    port=pm.port,
                    map_to_port=pm.map_to_port,
                    app_name="lab" + str(i),
                )
            )
        apps.append(
            AppSpec(
                port=self.lab_port,
                map_to_port=get_map_to_port(self.ports, self.lab_port),
                app_name="lab",
                url_path="lab",
                url_query_params={"token": token},
            )
        )
        if self.openssh_server:
            OpenSSHExtension.patch_apps(
                apps, map_to_port=get_map_to_port(self.ports, OpenSSHExtension.port)
            )
        return [
            JobSpec(
                image_name=self.image_name,
                commands=self._commands(),
                entrypoint=["/bin/bash", "-i", "-c"],
                env=env,
                working_dir=self.working_dir,
                artifact_specs=self.artifact_specs,
                requirements=self.resources,
                app_specs=apps,
            )
        ]

    def _image_name(self) -> str:
        cuda_is_required = self.resources and self.resources.gpus
        cuda_image_name = f"dstackai/miniforge:py{self.python}-{version.miniforge_image}-cuda-11.1"
        cpu_image_name = f"dstackai/miniforge:py{self.python}-{version.miniforge_image}"
        return cuda_image_name if cuda_is_required else cpu_image_name

    def _commands(self):
        commands = []
        if self.env:
            self._extend_commands_with_env(commands, self.env)
        if self.openssh_server:
            OpenSSHExtension.patch_commands(commands, ssh_pub_key=self.ssh_key_pub)
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
                f'echo "c.ServerApp.port = {self.lab_port}" >> /root/.jupyter/jupyter_server_config.py',
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
