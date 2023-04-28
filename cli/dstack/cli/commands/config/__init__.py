from argparse import Namespace

from dstack.api.hub import HubClient, HubClientConfig
from dstack.cli.commands import BasicCommand
from dstack.cli.common import console
from dstack.cli.config import CLIConfigManager


class ConfigCommand(BasicCommand):
    NAME = "config"
    DESCRIPTION = "Configure hub"

    def __init__(self, parser):
        super(ConfigCommand, self).__init__(parser)

    def register(self):
        self._parser.add_argument("--project", type=str, help="", required=True)
        self._parser.add_argument("--url", type=str, help="Hub url")
        self._parser.add_argument("--token", type=str, help="Hub token")
        self._parser.add_argument(
            "--default",
            action="store_true",
            help="Make the project default. It will be used when --project is ommitted in commands.",
            default=False,
        )
        self._parser.add_argument(
            "--remove", action="store_true", help="Delete project configuration"
        )

    def _command(self, args: Namespace):
        cli_config_manager = CLIConfigManager()
        if args.remove:
            cli_config_manager.delete_project(args.project)
            cli_config_manager.save()
        else:
            if not args.url:
                console.print("Specify --url")
                exit(1)
            elif not args.token:
                console.print("Specify --token")
                exit(1)
            HubClient.validate_config(
                HubClientConfig(url=args.url, token=args.token), project=args.project
            )
            cli_config_manager.configure_project(
                name=args.project, url=args.url, token=args.token, default=args.default
            )
            cli_config_manager.save()
        console.print(f"[grey58]OK[/]")
