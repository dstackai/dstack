from argparse import ArgumentParser, Namespace
from typing import Any, Dict, List, Optional

from rich_argparse import RichHelpFormatter

import dstack.api.hub as hub
from dstack import version
from dstack._internal.core.app import AppSpec
from dstack._internal.core.job import JobSpec
from dstack._internal.providers import Provider
from dstack._internal.providers.extensions import OpenSSHExtension
from dstack._internal.providers.ports import filter_reserved_ports, get_map_to_port


class SSHProvider(Provider):
    def __init__(self):
        super().__init__("ssh")
        self.python = None
        self.env = None
        self.artifact_specs = None
        self.working_dir = None
        self.resources = None
        self.setup = None
        self.image_name = None
        self.home_dir = "/root"
        self.code = True
        self.setup = []

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
        self.python = self._safe_python_version("python")
        self.setup = self._get_list_data("setup") or []
        self.env = self._env()
        self.artifact_specs = self._artifact_specs()
        self.working_dir = self.provider_data.get("working_dir")
        self.resources = self._resources()
        self.image_name = self._image_name()
        self.code = self.code or self.provider_data.get("code", self.code)

    def _create_parser(self, workflow_name: Optional[str]) -> Optional[ArgumentParser]:
        parser = ArgumentParser(
            prog="dstack run " + (workflow_name or self.provider_name),
            formatter_class=RichHelpFormatter,
        )
        self._add_base_args(parser)
        parser.add_argument("--code", action="store_true", help="Print VS Code connection URI")
        return parser

    def parse_args(self):
        parser = self._create_parser(self.workflow_name)
        args, unknown_args = parser.parse_known_args(self.provider_args)
        self._parse_base_args(args, unknown_args)
        if args.code:
            self.code = True

    def create_job_specs(self) -> List[JobSpec]:
        apps = []
        for i, pm in enumerate(filter_reserved_ports(self.ports)):
            apps.append(
                AppSpec(
                    port=pm.port,
                    map_to_port=pm.map_to_port,
                    app_name="ssh" + (str(i) if len(self.ports) > 1 else ""),
                )
            )
        OpenSSHExtension.patch_apps(
            apps, map_to_port=get_map_to_port(self.ports, OpenSSHExtension.port)
        )
        return [
            JobSpec(
                image_name=self.image_name,
                commands=self._commands(),
                entrypoint=["/bin/bash", "-i", "-c"],
                working_dir=self.working_dir,
                artifact_specs=self.artifact_specs,
                requirements=self.resources,
                app_specs=apps,
                setup=self.setup,
            )
        ]

    def _image_name(self) -> str:
        cuda_is_required = self.resources and self.resources.gpus
        cuda_image_name = f"dstackai/miniforge:py{self.python}-{version.miniforge_image}-cuda-11.4"
        cpu_image_name = f"dstackai/miniforge:py{self.python}-{version.miniforge_image}"
        return cuda_image_name if cuda_is_required else cpu_image_name

    def _commands(self):
        commands = []
        if self.env:
            self._extend_commands_with_env(commands, self.env)
        OpenSSHExtension.patch_commands(commands, ssh_key_pub=self.ssh_key_pub)
        # TODO: Pre-install ipykernel and other VS Code extensions
        if self.code:
            commands.extend(
                [
                    "echo ''",
                    f"echo To open in VS Code Desktop, use one of these links:",
                    f"echo ''",
                    f"echo '  vscode://vscode-remote/ssh-remote+{self.run_name}/workflow'",
                    # f"echo '  vscode-insiders://vscode-remote/ssh-remote+{self.run_name}/workflow'",
                    "echo ''",
                    f"echo 'To connect via SSH, use: `ssh {self.run_name}`'",
                    "echo ''",
                    "echo -n 'To exit, press Ctrl+C.'",
                ]
            )
        commands.extend(
            [
                "cat",
            ]
        )
        return commands


def __provider__():
    return SSHProvider()
