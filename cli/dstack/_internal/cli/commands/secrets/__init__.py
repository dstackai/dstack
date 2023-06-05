from argparse import Namespace

from rich.prompt import Confirm, Prompt
from rich.table import Table
from rich_argparse import RichHelpFormatter

from dstack._internal.cli.commands import BasicCommand
from dstack._internal.cli.common import add_project_argument, check_init, console
from dstack._internal.cli.config import get_hub_client
from dstack._internal.core.secret import Secret


class SecretCommand(BasicCommand):
    NAME = "secrets"
    DESCRIPTION = "Manage secrets"

    def __init__(self, parser):
        super(SecretCommand, self).__init__(parser)

    def register(self):
        add_project_argument(self._parser)

        subparsers = self._parser.add_subparsers()
        list_parser = subparsers.add_parser(
            "list", help="List secrets", formatter_class=RichHelpFormatter
        )
        add_project_argument(list_parser)

        add_secrets_parser = subparsers.add_parser(
            "add", help="Add a secret", formatter_class=RichHelpFormatter
        )
        add_project_argument(add_secrets_parser)
        add_secrets_parser.add_argument(
            "secret_name", metavar="NAME", type=str, help="The name of the secret"
        )
        add_secrets_parser.add_argument(
            "secret_value",
            metavar="VALUE",
            type=str,
            help="The value of the secret",
            nargs="?",
        )
        add_secrets_parser.add_argument(
            "-y", "--yes", help="Don't ask for confirmation", action="store_true"
        )
        add_secrets_parser.set_defaults(func=self.add_secret)

        update_secrets_parser = subparsers.add_parser(
            "update", help="Update a secret", formatter_class=RichHelpFormatter
        )
        add_project_argument(update_secrets_parser)
        update_secrets_parser.add_argument(
            "secret_name", metavar="NAME", type=str, help="The name of the secret"
        )
        update_secrets_parser.add_argument(
            "secret_value",
            metavar="VALUE",
            type=str,
            help="The value of the secret",
            nargs="?",
        )
        update_secrets_parser.set_defaults(func=self.update_secret)

        delete_secrets_parser = subparsers.add_parser(
            "delete", help="Delete a secret", formatter_class=RichHelpFormatter
        )
        add_project_argument(delete_secrets_parser)
        delete_secrets_parser.add_argument(
            "secret_name", metavar="NAME", type=str, help="The name of the secret"
        )
        delete_secrets_parser.set_defaults(func=self.delete_secret)

    @check_init
    def add_secret(self, args: Namespace):
        hub_client = get_hub_client(project_name=args.project)
        secret_value = args.secret_value or Prompt.ask("Value", password=True)
        if hub_client.get_secret(args.secret_name):
            if args.yes or Confirm.ask(
                f"[red]The secret '{args.secret_name}' already exists. "
                f"Do you want to override it?[/]"
            ):
                hub_client.update_secret(
                    Secret(secret_name=args.secret_name, secret_value=secret_value)
                )
                console.print(f"[grey58]OK[/]")
            else:
                return
        else:
            hub_client.add_secret(Secret(secret_name=args.secret_name, secret_value=secret_value))
            console.print(f"[grey58]OK[/]")

    @check_init
    def update_secret(self, args: Namespace):
        hub_client = get_hub_client(project_name=args.project)
        secret_value = hub_client.get_secret(args.secret_name)
        if secret_value is None:
            console.print(f"The secret '{args.secret_name}' doesn't exist")
            exit(1)
        secret_value = args.secret_value or Prompt.ask("Value", password=True)
        hub_client.update_secret(Secret(secret_name=args.secret_name, secret_value=secret_value))
        console.print(f"[grey58]OK[/]")

    @check_init
    def delete_secret(self, args: Namespace):
        hub_client = get_hub_client(project_name=args.project)
        secret = hub_client.get_secret(args.secret_name)
        if secret is None:
            console.print(f"The secret '{args.secret_name}' doesn't exist")
            exit(1)
        if Confirm.ask(f" [red]Delete the secret '{secret.secret_name}'?[/]"):
            hub_client.delete_secret(secret.secret_name)
            console.print(f"[grey58]OK[/]")

    @check_init
    def _command(self, args: Namespace):
        table = Table(box=None)
        table.add_column("NAME", style="bold", no_wrap=True)
        hub_client = get_hub_client(project_name=args.project)
        secret_names = hub_client.list_secret_names()
        for secret_name in secret_names:
            table.add_row(secret_name)
        console.print(table)
