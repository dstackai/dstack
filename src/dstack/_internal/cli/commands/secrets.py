import argparse

from dstack._internal.cli.commands import APIBaseCommand
from dstack._internal.cli.services.completion import SecretNameCompleter
from dstack._internal.cli.utils.common import (
    confirm_ask,
    console,
)
from dstack._internal.cli.utils.secrets import print_secrets_table


class SecretCommand(APIBaseCommand):
    NAME = "secret"
    DESCRIPTION = "Manage secrets"

    def _register(self):
        super()._register()
        self._parser.set_defaults(subfunc=self._list)
        subparsers = self._parser.add_subparsers(dest="action")

        list_parser = subparsers.add_parser(
            "list", help="List secrets", formatter_class=self._parser.formatter_class
        )
        list_parser.set_defaults(subfunc=self._list)

        get_parser = subparsers.add_parser(
            "get", help="Get secret value", formatter_class=self._parser.formatter_class
        )
        get_parser.add_argument(
            "name",
            help="The name of the secret",
        ).completer = SecretNameCompleter()  # type: ignore[attr-defined]
        get_parser.set_defaults(subfunc=self._get)

        set_parser = subparsers.add_parser(
            "set", help="Set secret", formatter_class=self._parser.formatter_class
        )
        set_parser.add_argument(
            "name",
            help="The name of the secret",
        )
        set_parser.add_argument(
            "value",
            help="The value of the secret",
        )
        set_parser.set_defaults(subfunc=self._set)

        delete_parser = subparsers.add_parser(
            "delete",
            help="Delete secrets",
            formatter_class=self._parser.formatter_class,
        )
        delete_parser.add_argument(
            "name",
            help="The name of the secret",
        ).completer = SecretNameCompleter()  # type: ignore[attr-defined]
        delete_parser.add_argument(
            "-y", "--yes", help="Don't ask for confirmation", action="store_true"
        )
        delete_parser.set_defaults(subfunc=self._delete)

    def _command(self, args: argparse.Namespace):
        super()._command(args)
        args.subfunc(args)

    def _list(self, args: argparse.Namespace):
        secrets = self.api.client.secrets.list(self.api.project)
        print_secrets_table(secrets)

    def _get(self, args: argparse.Namespace):
        secret = self.api.client.secrets.get(self.api.project, name=args.name)
        print_secrets_table([secret])

    def _set(self, args: argparse.Namespace):
        self.api.client.secrets.create_or_update(
            self.api.project,
            name=args.name,
            value=args.value,
        )
        console.print("[grey58]OK[/]")

    def _delete(self, args: argparse.Namespace):
        if not args.yes and not confirm_ask(f"Delete the secret [code]{args.name}[/]?"):
            console.print("\nExiting...")
            return

        with console.status("Deleting secret..."):
            self.api.client.secrets.delete(
                project_name=self.api.project,
                names=[args.name],
            )
        console.print("[grey58]OK[/]")
