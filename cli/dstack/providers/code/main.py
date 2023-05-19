import uuid
from argparse import ArgumentParser, Namespace
from typing import Any, Dict, List, Optional

from rich_argparse import RichHelpFormatter

import dstack.api.hub as hub
from dstack import version
from dstack.core.app import AppSpec
from dstack.core.job import JobSpec
from dstack.providers import Provider


class CodeProvider(Provider):
    def __init__(self):
        super().__init__("code")
        self.setup = None
        self.ports = None
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
        self.ports = self.provider_data.get("ports")
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
        parser.add_argument("-p", "--ports", metavar="PORT_COUNT", type=int)
        return parser

    def parse_args(self):
        parser = self._create_parser(self.workflow_name)
        args, unknown_args = parser.parse_known_args(self.provider_args)
        self._parse_base_args(args, unknown_args)
        if args.openssh_server:
            self.openssh_server = True
        if args.ports:
            self.provider_data["ports"] = args.ports

    def create_job_specs(self) -> List[JobSpec]:
        env = {}
        connection_token = uuid.uuid4().hex
        env["CONNECTION_TOKEN"] = connection_token
        apps = [
            AppSpec(
                port_index=0,
                app_name="code",
                url_query_params={
                    "tkn": connection_token,
                },
            )
        ]
        for i in range(self.ports or 0):
            apps.append(
                AppSpec(
                    port_index=i + 1,
                    app_name="code" + (str(i + 1)),
                )
            )
        if self.openssh_server:
            apps.append(AppSpec(port_index=len(apps), app_name="openssh-server"))
        return [
            JobSpec(
                image_name=self.image_name,
                commands=self._commands(),
                entrypoint=["/bin/bash", "-i", "-c"],
                env=env,
                working_dir=self.working_dir,
                artifact_specs=self.artifact_specs,
                port_count=len(apps),
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
            self._extend_commands_with_openssh_server(commands, self.ssh_key_pub, 1)
        commands.append("export _PORT=$PORT_0")
        if self.ports:
            for i in range(self.ports):
                commands.append(f"export PORT_{i}=$PORT_{i + 1}")
                commands.append(f"echo 'export PORT_{i}=\"$PORT_{i + 1}\"' >> ~/.bashrc")
                commands.append(f'echo "The PORT_{i} port is mapped to http://0.0.0.0:$PORT_{i}"')
            commands.append("echo")
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
            f"/tmp/openvscode-server-v{self.version}-linux-$arch/bin/openvscode-server --port $_PORT --host 0.0.0.0 --connection-token $CONNECTION_TOKEN --default-folder /workflow"
        )
        return commands


def __provider__():
    return CodeProvider()
