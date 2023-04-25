import os
from argparse import Namespace

from rich.prompt import Confirm, Prompt
from rich.table import Table
from rich_argparse import RichHelpFormatter

from dstack.api.hub import HubClient
from dstack.cli.commands import BasicCommand
from dstack.cli.common import check_backend, check_config, check_git, check_init, console
from dstack.cli.config import config
from dstack.core.repo import RemoteRepo
from dstack.core.secret import Secret


class SecretCommand(BasicCommand):
    NAME = "secrets"
    DESCRIPTION = "Manage secrets"

    def __init__(self, parser):
        super(SecretCommand, self).__init__(parser)

    def register(self):
        subparsers = self._parser.add_subparsers()

        subparsers.add_parser("list", help="List secrets", formatter_class=RichHelpFormatter)

        add_secrets_parser = subparsers.add_parser(
            "add", help="Add a secret", formatter_class=RichHelpFormatter
        )
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

        delete_secrets_parser = subparsers.add_parser("delete", help="Delete a secret")
        delete_secrets_parser.add_argument(
            "secret_name", metavar="NAME", type=str, help="The name of the secret"
        )
        delete_secrets_parser.set_defaults(func=self.delete_secret)

    @check_config
    @check_git
    @check_backend
    @check_init
    def add_secret(self, args: Namespace):
        repo = RemoteRepo(repo_ref=config.repo_user_config.repo_ref, local_repo_dir=os.getcwd())
        hub_client = HubClient(repo=repo)
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

    @check_config
    @check_git
    @check_backend
    @check_init
    def update_secret(self, args: Namespace):
        repo = RemoteRepo(repo_ref=config.repo_user_config.repo_ref, local_repo_dir=os.getcwd())
        hub_client = HubClient(repo=repo)
        secret_value = hub_client.get_secret(args.secret_name)
        if secret_value is None:
            console.print(f"The secret '{args.secret_name}' doesn't exist")
            exit(1)
        secret_value = args.secret_value or Prompt.ask("Value", password=True)
        hub_client.update_secret(Secret(secret_name=args.secret_name, secret_value=secret_value))
        console.print(f"[grey58]OK[/]")

    @check_config
    @check_git
    @check_backend
    @check_init
    def delete_secret(self, args: Namespace):
        repo = RemoteRepo(repo_ref=config.repo_user_config.repo_ref, local_repo_dir=os.getcwd())
        hub_client = HubClient(repo=repo)
        secret = hub_client.get_secret(args.secret_name)
        if secret is None:
            console.print(f"The secret '{args.secret_name}' doesn't exist")
        if Confirm.ask(f" [red]Delete the secret '{secret.secret_name}'?[/]"):
            hub_client.delete_secret(secret.secret_name)
            console.print(f"[grey58]OK[/]")

    @check_config
    @check_git
    @check_backend
    @check_init
    def _command(self, args: Namespace):
        table = Table(box=None)
        table.add_column("NAME", style="bold", no_wrap=True)
        repo = RemoteRepo(repo_ref=config.repo_user_config.repo_ref, local_repo_dir=os.getcwd())
        hub_client = HubClient(repo=repo)
        secret_names = hub_client.list_secret_names()
        for secret_name in secret_names:
            table.add_row(secret_name)
        console.print(table)
