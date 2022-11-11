import sys
from argparse import Namespace

from rich import print
from rich.console import Console
from rich.prompt import Confirm, Prompt
from rich.table import Table

from dstack.backend import load_backend, Secret
from dstack.config import ConfigError
from dstack.repo import load_repo_data


def list_secrets_func(_: Namespace):
    try:
        backend = load_backend()
        repo_data = load_repo_data()
        secret_names = backend.list_secret_names(repo_data)
        console = Console()
        table = Table(box=None)
        table.add_column("NAME", style="bold", no_wrap=True)
        for secret_name in secret_names:
            table.add_row(
                secret_name
            )
        console.print(table)
    except ConfigError:
        sys.exit(f"Call 'dstack config' first")


def add_secret_func(args: Namespace):
    try:
        backend = load_backend()
        repo_data = load_repo_data()
        if backend.get_secret(repo_data, args.secret_name):
            if args.yes or Confirm.ask(f"[red]The secret '{args.secret_name}' already exists. "
                                       f"Do you want to override it?[/]"):
                secret_value = args.secret_value or Prompt.ask("Value", password=True)
                backend.update_secret(repo_data, Secret(args.secret_name, secret_value))
                print(f"[grey58]OK[/]")
            else:
                return
        else:
            secret_value = args.secret_value or Prompt.ask("Value", password=True)
            backend.add_secret(repo_data, Secret(args.secret_name, secret_value))
            print(f"[grey58]OK[/]")
    except ConfigError:
        sys.exit(f"Call 'dstack config' first")


def update_secret_func(args: Namespace):
    try:
        backend = load_backend()
        repo_data = load_repo_data()
        if not backend.get_secret(repo_data, args.secret_name):
            sys.exit(f"The secret '{args.secret_name}' doesn't exist")
        else:
            secret_value = args.secret_value or Prompt.ask("Value", password=True)
            backend.update_secret(repo_data, Secret(args.secret_name, secret_value))
            print(f"[grey58]OK[/]")
    except ConfigError:
        sys.exit(f"Call 'dstack config' first")


def delete_secret_func(args: Namespace):
    try:
        backend = load_backend()
        repo_data = load_repo_data()
        secret = backend.get_secret(repo_data, args.secret_name)
        if not secret:
            sys.exit(f"The secret '{args.secret_name}' doesn't exist")
        elif Confirm.ask(f" [red]Delete the secret '{secret.secret_name}'?[/]"):
            backend.delete_secret(repo_data, secret.secret_name)
            print(f"[grey58]OK[/]")
    except ConfigError:
        sys.exit(f"Call 'dstack config' first")


def register_parsers(main_subparsers):
    parser = main_subparsers.add_parser("secrets", help="Manage secrets")
    parser.set_defaults(func=list_secrets_func)

    subparsers = parser.add_subparsers()

    subparsers.add_parser("list", help="List secrets")

    add_secrets_parser = subparsers.add_parser("add", help="Add a secret")
    add_secrets_parser.add_argument("secret_name", metavar="NAME", type=str, help="The name of the secret")
    add_secrets_parser.add_argument("secret_value", metavar="VALUE", type=str, help="The value of the secret",
                                    nargs="?")
    add_secrets_parser.add_argument("-y", "--yes", help="Don't ask for confirmation", action="store_true")
    add_secrets_parser.set_defaults(func=add_secret_func)

    update_secrets_parser = subparsers.add_parser("update", help="Update a secret")
    update_secrets_parser.add_argument("secret_name", metavar="NAME", type=str, help="The name of the secret")
    update_secrets_parser.add_argument("secret_value", metavar="VALUE", type=str, help="The value of the secret",
                                       nargs="?")
    update_secrets_parser.set_defaults(func=update_secret_func)

    delete_secrets_parser = subparsers.add_parser("delete", help="Delete a secret")
    delete_secrets_parser.add_argument("secret_name", metavar="NAME", type=str, help="The name of the secret")
    delete_secrets_parser.set_defaults(func=delete_secret_func)
