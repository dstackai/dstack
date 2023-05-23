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


class CodeProvider(Provider):
    code_port = 10000

    def __init__(self):
        super().__init__("code")
        self.setup = None
        self.python = None
        self.version = None
        self.requirements = None
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
        self.version = self.provider_data.get("version") or "1.78.1"
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
        connection_token = uuid.uuid4().hex
        env["CONNECTION_TOKEN"] = connection_token
        apps = []
        for i, pm in enumerate(filter_reserved_ports(self.ports), start=1):
            apps.append(
                AppSpec(
                    port=pm.port,
                    map_to_port=pm.map_to_port,
                    app_name="code" + str(i),
                )
            )
        apps.append(
            AppSpec(
                port=self.code_port,
                map_to_port=get_map_to_port(self.ports, self.code_port),
                app_name="code",
                url_query_params={
                    "tkn": connection_token,
                },
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
            OpenSSHExtension.patch_commands(commands, ssh_key_pub=self.ssh_key_pub)
        commands.extend(
            [
                "pip install ipykernel -q",
                "mkdir -p /tmp",
                'if [ $(uname -m) = "aarch64" ]; then arch="arm64"; else arch="x64"; fi',
                f"wget -q https://github.com/gitpod-io/openvscode-server/releases/download/"
                f"openvscode-server-v{self.version}/openvscode-server-v{self.version}-linux-$arch.tar.gz -O "
                f"/tmp/openvscode-server-v{self.version}-linux-$arch.tar.gz",
                f"tar -xzf /tmp/openvscode-server-v{self.version}-linux-$arch.tar.gz -C /tmp",
                f"/tmp/openvscode-server-v{self.version}-linux-$arch/bin/openvscode-server --install-extension ms-python.python --install-extension ms-toolsai.jupyter",
                "rm /usr/bin/python2*",
            ]
        )
        if self.setup:
            commands.extend(self.setup)
        commands.append(
            f"/tmp/openvscode-server-v{self.version}-linux-$arch/bin/openvscode-server"
            f"  --port {self.code_port} --host 0.0.0.0 --connection-token $CONNECTION_TOKEN"
            f"  --default-folder /workflow"
        )
        return commands


def __provider__():
    return CodeProvider()
