from argparse import ArgumentParser
from typing import Any, Dict, List, Optional

from rich_argparse import RichHelpFormatter

from dstack import version
from dstack.backend.base import Backend
from dstack.core.app import AppSpec
from dstack.core.job import JobSpec
from dstack.providers import Provider


class BashProvider(Provider):
    def __init__(self):
        super().__init__("bash")
        self.file = None
        self.python = None
        self.env = None
        self.artifact_specs = None
        self.working_dir = None
        self.resources = None
        self.ports = None
        self.commands = None
        self.image_name = None
        self.home_dir = "/root"

    def load(
        self,
        backend: Backend,
        provider_args: List[str],
        workflow_name: Optional[str],
        provider_data: Dict[str, Any],
        run_name: str,
    ):
        super().load(backend, provider_args, workflow_name, provider_data, run_name)
        self.python = self._safe_python_version("python")
        self.commands = self._get_list_data("commands")
        self.env = self._env()
        self.artifact_specs = self._artifact_specs()
        self.working_dir = self.provider_data.get("working_dir")
        self.ports = self.provider_data.get("ports")
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
        if not workflow_name:
            parser.add_argument("-c", "--command", type=str)
        return parser

    def parse_args(self):
        parser = self._create_parser(self.workflow_name)
        args, unknown_args = parser.parse_known_args(self.provider_args)
        self._parse_base_args(args, unknown_args)
        if self.run_as_provider:
            self.provider_data["commands"] = [args.command]
        if args.ports:
            self.provider_data["ports"] = args.ports
        if args.openssh_server:
            self.openssh_server = True

    def create_job_specs(self) -> List[JobSpec]:
        apps = []
        for i in range(self.ports or 0):
            apps.append(
                AppSpec(
                    port_index=i,
                    app_name="bash" + (str(i) if self.ports > 1 else ""),
                )
            )
        if self.openssh_server:
            apps.append(AppSpec(port_index=len(apps), app_name="openssh-server"))
        return [
            JobSpec(
                image_name=self.image_name,
                commands=self._commands(),
                entrypoint=["/bin/bash", "-i", "-c"],
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
            self._extend_commands_with_openssh_server(commands, self.ssh_key_pub, self.ports or 0)
        commands.extend(self.commands)
        return commands


def __provider__():
    return BashProvider()
