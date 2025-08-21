import argparse

from requests import HTTPError
from rich.table import Table

import dstack.api.server
from dstack._internal.cli.commands import BaseCommand
from dstack._internal.cli.utils.common import confirm_ask, console
from dstack._internal.core.errors import ClientError, CLIError
from dstack._internal.core.services.configs import ConfigManager
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


class ProjectCommand(BaseCommand):
    NAME = "project"
    DESCRIPTION = "Manage projects configs"

    def _register(self):
        super()._register()
        subparsers = self._parser.add_subparsers(dest="subcommand", help="Command to execute")

        # Add subcommand
        add_parser = subparsers.add_parser("add", help="Add or update a project config")
        add_parser.add_argument(
            "--name", type=str, help="The name of the project to configure", required=True
        )
        add_parser.add_argument("--url", type=str, help="Server url", required=True)
        add_parser.add_argument("--token", type=str, help="User token", required=True)
        add_parser.add_argument(
            "-y",
            "--yes",
            help="Don't ask for confirmation (e.g. update the config)",
            action="store_true",
        )
        add_parser.add_argument(
            "-n",
            "--no",
            help="Don't ask for confirmation (e.g. do not update the config)",
            action="store_true",
        )
        add_parser.set_defaults(subfunc=self._add)

        # Delete subcommand
        delete_parser = subparsers.add_parser("delete", help="Delete a project config")
        delete_parser.add_argument(
            "--name", type=str, help="The name of the project to delete", required=True
        )
        delete_parser.add_argument(
            "-y",
            "--yes",
            help="Don't ask for confirmation",
            action="store_true",
        )
        delete_parser.set_defaults(subfunc=self._delete)

        # List subcommand
        list_parser = subparsers.add_parser("list", help="List configured projects")
        list_parser.set_defaults(subfunc=self._list)

        # Set default subcommand
        set_default_parser = subparsers.add_parser("set-default", help="Set default project")
        set_default_parser.add_argument(
            "name", type=str, help="The name of the project to set as default"
        )
        set_default_parser.set_defaults(subfunc=self._set_default)

    def _command(self, args: argparse.Namespace):
        if not hasattr(args, "subfunc"):
            args.subfunc = self._list
        args.subfunc(args)

    def _add(self, args: argparse.Namespace):
        config_manager = ConfigManager()
        api_client = dstack.api.server.APIClient(base_url=args.url, token=args.token)
        try:
            api_client.projects.get(args.name)
        except HTTPError as e:
            if e.response.status_code == 403:
                raise CLIError("Forbidden. Ensure the token is valid.")
            elif e.response.status_code == 404:
                raise CLIError(f"Project '{args.name}' not found.")
            else:
                raise e
        default_project = config_manager.get_project_config()
        if (
            default_project is None
            or default_project.name != args.name
            or default_project.url != args.url
            or default_project.token != args.token
        ):
            set_it_as_default = (
                (
                    args.yes
                    or not default_project
                    or confirm_ask(f"Set '{args.name}' as your default project?")
                )
                if not args.no
                else False
            )
            config_manager.configure_project(
                name=args.name, url=args.url, token=args.token, default=set_it_as_default
            )
            config_manager.save()
        logger.info(
            f"Configuration updated at {config_manager.config_filepath}", {"show_path": False}
        )

    def _delete(self, args: argparse.Namespace):
        config_manager = ConfigManager()
        if args.yes or confirm_ask(f"Are you sure you want to delete project '{args.name}'?"):
            config_manager.delete_project(args.name)
            config_manager.save()
            console.print("[grey58]OK[/]")

    def _list(self, args: argparse.Namespace):
        config_manager = ConfigManager()
        default_project = config_manager.get_project_config()

        table = Table(box=None)
        table.add_column("PROJECT", style="bold", no_wrap=True)
        table.add_column("URL", style="grey58")
        table.add_column("USER", style="grey58")
        table.add_column("DEFAULT", justify="center")

        for project_config in config_manager.list_project_configs():
            project_name = project_config.name
            is_default = project_name == default_project.name if default_project else False

            # Get username from API
            try:
                api_client = dstack.api.server.APIClient(
                    base_url=project_config.url, token=project_config.token
                )
                user_info = api_client.users.get_my_user()
                username = user_info.username
            except ClientError:
                username = "(invalid token)"

            table.add_row(
                project_name,
                project_config.url,
                username,
                "✓" if is_default else "",
                style="bold" if is_default else None,
            )

        console.print(table)

    def _set_default(self, args: argparse.Namespace):
        config_manager = ConfigManager()
        project_config = config_manager.get_project_config(args.name)
        if project_config is None:
            raise CLIError(f"Project '{args.name}' not found")

        config_manager.configure_project(
            name=args.name, url=project_config.url, token=project_config.token, default=True
        )
        config_manager.save()
        console.print("[grey58]OK[/]")
