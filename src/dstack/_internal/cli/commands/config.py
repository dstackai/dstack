import argparse

from requests import HTTPError

import dstack.api.server
from dstack._internal.cli.commands import BaseCommand
from dstack._internal.cli.utils.common import console
from dstack._internal.core.errors import ClientError, CLIError
from dstack._internal.core.services.configs import ConfigManager


class ConfigCommand(BaseCommand):
    NAME = "config"
    DESCRIPTION = "Configure projects"

    def _register(self):
        super()._register()
        self._parser.add_argument(
            "--project", type=str, help="The name of the project to configure"
        )
        self._parser.add_argument("--url", type=str, help="Server url")
        self._parser.add_argument("--token", type=str, help="User token")
        self._parser.add_argument(
            "--default",
            action="store_true",
            help="Make the project default. It will be used when --project is ommitted in commands.",
            default=False,
        )
        self._parser.add_argument(
            "--remove", action="store_true", help="Delete project configuration"
        )

    def _command(self, args: argparse.Namespace):
        config_manager = ConfigManager()
        if args.remove:
            config_manager.delete_project(args.project)
            config_manager.save()
            console.print(f"[grey58]OK[/]")
            return

        if not args.url:
            console.print("Specify --url")
            exit(1)
        elif not args.token:
            console.print("Specify --token")
            exit(1)
        api_client = dstack.api.server.APIClient(base_url=args.url, token=args.token)
        try:
            api_client.projects.get(args.project)
        except HTTPError as e:
            if e.response.status_code == 403:
                raise CLIError("Forbidden. Ensure the token is valid.")
            elif e.response.status_code == 404:
                raise CLIError(f"Project '{args.project}' not found.")
            else:
                raise e
        config_manager.configure_project(
            name=args.project, url=args.url, token=args.token, default=args.default
        )
        config_manager.save()
        console.print(f"[grey58]OK[/]")
