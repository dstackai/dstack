from argparse import ArgumentParser, Namespace
from typing import Any, Dict, List, Optional

from rich_argparse import RichHelpFormatter

import dstack.api.hub as hub
from dstack.core.app import AppSpec
from dstack.core.job import JobSpec
from dstack.providers import Provider
from dstack.providers.ports import filter_reserved_ports


class DockerProvider(Provider):
    def __init__(self):
        super().__init__("docker")
        self.image_name = None
        self.registry_auth = None
        self.commands = None
        self.entrypoint = None
        self.artifact_specs = None
        self.env = None
        self.working_dir = None
        self.resources = None

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
        self.image_name = self.provider_data["image"]
        self.registry_auth = self.provider_data.get("registry_auth")
        self.commands = self._get_list_data("commands")
        self.entrypoint = self._get_entrypoint()
        if self.commands and self.entrypoint is None:  # commands not empty
            self.entrypoint = ["/bin/sh", "-i", "-c"]
        self.artifact_specs = self._artifact_specs()
        self.env = self.provider_data.get("env")
        self.home_dir = self.provider_data.get("home_dir")
        self.working_dir = self.provider_data.get("working_dir")
        self.resources = self._resources()

    def _create_parser(self, workflow_name: Optional[str]) -> Optional[ArgumentParser]:
        parser = ArgumentParser(
            prog="dstack run " + (workflow_name or self.provider_name),
            formatter_class=RichHelpFormatter,
        )
        self._add_base_args(parser)
        if not workflow_name:
            parser.add_argument("image", metavar="IMAGE", type=str)
            parser.add_argument("-c", "--command", type=str)
            parser.add_argument("-e", "--entrypoint", type=str)
        return parser

    def parse_args(self):
        parser = self._create_parser(self.workflow_name)
        args, unknown_args = parser.parse_known_args(self.provider_args)
        self._parse_base_args(args, unknown_args)
        if self.run_as_provider:
            self.provider_data["image"] = args.image
            if args.command:
                self.provider_data["commands"] = [args.command]
            if args.entrypoint:
                self.provider_data["entrypoint"] = args.entrypoint

    def create_job_specs(self) -> List[JobSpec]:
        apps = []
        for i, pm in enumerate(filter_reserved_ports(self.ports)):
            apps.append(
                AppSpec(
                    port=pm.port,
                    map_to_port=pm.map_to_port,
                    app_name="docker" + (str(i) if len(self.ports) > 1 else ""),
                )
            )
        commands = []
        commands.extend(self.commands or [])
        return [
            JobSpec(
                image_name=self.image_name,
                registry_auth=self.registry_auth,
                commands=commands,
                entrypoint=self.entrypoint,
                env=self.env,
                working_dir=self.working_dir,
                artifact_specs=self.artifact_specs,
                requirements=self.resources,
                app_specs=apps,
            )
        ]


def __provider__():
    return DockerProvider()
