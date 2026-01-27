import argparse
import sys
from typing import Any, Optional, Union

import questionary
from requests import HTTPError
from rich.table import Table

import dstack.api.server
from dstack._internal.cli.commands import BaseCommand
from dstack._internal.cli.utils.common import add_row_from_dict, confirm_ask, console
from dstack._internal.core.errors import ClientError, CLIError
from dstack._internal.core.models.config import ProjectConfig
from dstack._internal.core.services.configs import ConfigManager
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)

is_project_menu_supported = sys.stdin.isatty()


def select_default_project(
    project_configs: list[ProjectConfig], default_project: Optional[ProjectConfig]
) -> Optional[ProjectConfig]:
    """Show an interactive menu to select a default project.

    This method only prompts for selection and does not update the configuration.
    Use `ConfigManager.configure_project()` and `ConfigManager.save()` to persist
    the selected project as default.

    Args:
        project_configs: Non-empty list of available project configurations.
        default_project: Currently default project, if any.

    Returns:
        Selected project configuration, or None if cancelled.

    Raises:
        CLIError: If `is_project_menu_supported` is False or `project_configs` is empty.
    """
    if not is_project_menu_supported:
        raise CLIError("Interactive menu is not supported on this platform")

    if len(project_configs) == 0:
        raise CLIError("No projects configured")

    menu_entries = []
    default_index = None
    for i, project_config in enumerate(project_configs):
        is_default = project_config.name == default_project.name if default_project else False
        entry = f"{project_config.name} ({project_config.url})"
        if is_default:
            default_index = i
        menu_entries.append((entry, i))

    choices = [questionary.Choice(title=entry, value=index) for entry, index in menu_entries]
    default_value = default_index
    selected_index = questionary.select(
        message="Select the default project:",
        choices=choices,
        default=default_value,  # pyright: ignore[reportArgumentType]
        qmark="",
        instruction="(↑↓ Enter)",
    ).ask()

    if selected_index is not None and isinstance(selected_index, int):
        return project_configs[selected_index]
    return None


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
        for parser in [self._parser, list_parser]:
            parser.add_argument(
                "-v", "--verbose", action="store_true", help="Show more information"
            )

        # Set default subcommand
        set_default_parser = subparsers.add_parser("set-default", help="Set default project")
        set_default_parser.add_argument(
            "name",
            type=str,
            nargs="?" if is_project_menu_supported else None,
            help="The name of the project to set as default",
        )
        set_default_parser.set_defaults(subfunc=self._set_default)

    def _command(self, args: argparse.Namespace):
        super()._command(args)
        if not hasattr(args, "subfunc"):
            args.subfunc = self._project
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
        if args.verbose:
            table.add_column("USER", style="grey58")
        table.add_column("DEFAULT", justify="center")

        for project_config in config_manager.list_project_configs():
            project_name = project_config.name
            is_default = project_name == default_project.name if default_project else False
            row: dict[Union[str, int], Any] = {
                "PROJECT": project_name,
                "URL": project_config.url,
                "DEFAULT": "✓" if is_default else "",
            }

            if args.verbose:
                # Get username from API
                try:
                    api_client = dstack.api.server.APIClient(
                        base_url=project_config.url, token=project_config.token
                    )
                    user_info = api_client.users.get_my_user()
                    username = user_info.username
                except ClientError:
                    username = "(invalid token)"
                row["USER"] = username

            add_row_from_dict(table, row, style="bold" if is_default else None)

        console.print(table)

    def _project(self, args: argparse.Namespace):
        if is_project_menu_supported and not getattr(args, "verbose", False):
            config_manager = ConfigManager()
            project_configs = config_manager.list_project_configs()
            default_project = config_manager.get_project_config()
            selected_project = select_default_project(project_configs, default_project)
            if selected_project is not None:
                config_manager.configure_project(
                    name=selected_project.name,
                    url=selected_project.url,
                    token=selected_project.token,
                    default=True,
                )
                config_manager.save()
                console.print("[grey58]OK[/]")
        else:
            self._list(args)

    def _set_default(self, args: argparse.Namespace):
        if args.name:
            config_manager = ConfigManager()
            project_config = config_manager.get_project_config(args.name)
            if project_config is None:
                raise CLIError(f"Project '{args.name}' not found")

            config_manager.configure_project(
                name=args.name, url=project_config.url, token=project_config.token, default=True
            )
            config_manager.save()
            console.print("[grey58]OK[/]")
        else:
            config_manager = ConfigManager()
            project_configs = config_manager.list_project_configs()
            default_project = config_manager.get_project_config()
            selected_project = select_default_project(project_configs, default_project)
            if selected_project is not None:
                config_manager.configure_project(
                    name=selected_project.name,
                    url=selected_project.url,
                    token=selected_project.token,
                    default=True,
                )
                config_manager.save()
                console.print("[grey58]OK[/]")
