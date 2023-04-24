import sys
from argparse import Namespace

from rich import print
from rich.console import Console
from rich.prompt import Confirm, Prompt
from rich.table import Table
from rich_argparse import RichHelpFormatter

from dstack.api.backend import list_backends
from dstack.api.repos import load_repo
from dstack.cli.commands import BasicCommand
from dstack.cli.common import check_backend, check_config, check_git, check_init
from dstack.cli.config import config
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
        repo = load_repo(config.repo_user_config)
        secret_value = args.secret_value or Prompt.ask("Value", password=True)
        for backend in list_backends(repo):
            if backend.get_secret(args.secret_name):
                if args.yes or Confirm.ask(
                    f"[red]The secret '{args.secret_name}' (backend: {backend.name}) already exists. "
                    f"Do you want to override it?[/]"
                ):
                    backend.update_secret(
                        Secret(secret_name=args.secret_name, secret_value=secret_value)
                    )
                    print(f"[grey58]OK (backend: {backend.name})[/]")
                else:
                    return
            else:
                backend.add_secret(Secret(secret_name=args.secret_name, secret_value=secret_value))
                print(f"[grey58]OK (backend: {backend.name})[/]")

    @check_config
    @check_git
    @check_backend
    @check_init
    def update_secret(self, args: Namespace):
        repo = load_repo(config.repo_user_config)
        secret_value = None
        for backend in list_backends(repo):
            if backend.get_secret(args.secret_name):
                if secret_value is None:
                    secret_value = args.secret_value or Prompt.ask("Value", password=True)
                backend.update_secret(
                    Secret(secret_name=args.secret_name, secret_value=secret_value)
                )
                print(f"[grey58]OK (backend: {backend.name})[/]")
        if secret_value is None:
            sys.exit(f"The secret '{args.secret_name}' doesn't exist")

    @check_config
    @check_git
    @check_backend
    @check_init
    def delete_secret(self, args: Namespace):
        repo = load_repo(config.repo_user_config)
        anyone = False
        for backend in list_backends(repo):
            secret = backend.get_secret(args.secret_name)
            if not (secret is None) and Confirm.ask(
                f" [red]Delete the secret '{secret.secret_name}'"
                f"  (backend: {backend.name})?[/]"
            ):
                anyone = True
                backend.delete_secret(secret.secret_name)
                print(f"[grey58]OK[/]")
        if not anyone:
            sys.exit(f"The secret '{args.secret_name}' doesn't exist")

    @check_config
    @check_git
    @check_backend
    @check_init
    def _command(self, args: Namespace):
        console = Console()
        table = Table(box=None)
        repo = load_repo(config.repo_user_config)
        table.add_column("NAME", style="bold", no_wrap=True)
        table.add_column("BACKEND", style="bold", no_wrap=True)
        secrets = {}
        for backend in list_backends(repo):
            secret_names = backend.list_secret_names()
            for secret_name in secret_names:
                if secrets.get(secret_name) is None:
                    secrets[secret_name] = [backend.name]
                else:
                    secrets[secret_name].append(backend.name)
        for secret_name, secret_backend in secrets.items():
            table.add_row(secret_name, ",".join(secret_backend))
        console.print(table)
