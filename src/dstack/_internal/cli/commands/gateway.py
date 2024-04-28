import argparse

from dstack._internal.cli.commands import APIBaseCommand
from dstack._internal.cli.utils.common import confirm_ask, console
from dstack._internal.cli.utils.gateway import print_gateways_table
from dstack._internal.core.models.backends.base import BackendType


class GatewayCommand(APIBaseCommand):
    NAME = "gateway"
    DESCRIPTION = "Manage gateways"

    def _register(self):
        super()._register()
        self._parser.set_defaults(subfunc=self._list)
        subparsers = self._parser.add_subparsers(dest="action")

        list_parser = subparsers.add_parser(
            "list", help="List gateways", formatter_class=self._parser.formatter_class
        )
        list_parser.add_argument(
            "-v", "--verbose", action="store_true", help="Show more information"
        )
        list_parser.set_defaults(subfunc=self._list)

        create_parser = subparsers.add_parser(
            "create", help="Add a gateway", formatter_class=self._parser.formatter_class
        )
        create_parser.set_defaults(subfunc=self._create)
        create_parser.add_argument(
            "--backend", choices=["aws", "azure", "gcp", "kubernetes"], required=True
        )
        create_parser.add_argument("--region", required=True)
        create_parser.add_argument(
            "--set-default", action="store_true", help="Set as default gateway for the project"
        )
        create_parser.add_argument("--name", help="Set a custom name for the gateway")
        create_parser.add_argument(
            "--domain", help="Set the domain for the gateway", required=True
        )

        delete_parser = subparsers.add_parser(
            "delete", help="Delete a gateway", formatter_class=self._parser.formatter_class
        )
        delete_parser.set_defaults(subfunc=self._delete)
        delete_parser.add_argument("name", help="The name of the gateway")
        delete_parser.add_argument(
            "-y", "--yes", action="store_true", help="Don't ask for confirmation"
        )

        update_parser = subparsers.add_parser(
            "update", help="Update a gateway", formatter_class=self._parser.formatter_class
        )
        update_parser.set_defaults(subfunc=self._update)
        update_parser.add_argument("name", help="The name of the gateway")
        update_parser.add_argument(
            "--set-default", action="store_true", help="Set it the default gateway for the project"
        )
        update_parser.add_argument("--domain", help="Set the domain for the gateway")

    def _command(self, args: argparse.Namespace):
        super()._command(args)
        # TODO handle errors
        args.subfunc(args)

    def _list(self, args: argparse.Namespace):
        gateways = self.api.client.gateways.list(self.api.project)
        print_gateways_table(gateways, verbose=getattr(args, "verbose", False))

    def _create(self, args: argparse.Namespace):
        with console.status("Creating gateway..."):
            gateway = self.api.client.gateways.create(
                self.api.project, args.name, BackendType(args.backend), args.region
            )
            if args.set_default:
                self.api.client.gateways.set_default(self.api.project, gateway.name)
            if args.domain:
                self.api.client.gateways.set_wildcard_domain(
                    self.api.project, gateway.name, args.domain
                )
        gateway = self.api.client.gateways.get(self.api.project, gateway.name)
        print_gateways_table([gateway])

    def _delete(self, args: argparse.Namespace):
        gateway = self.api.client.gateways.get(self.api.project, args.name)
        print_gateways_table([gateway])
        if args.yes or confirm_ask("Do you want to delete the gateway?"):
            with console.status("Deleting gateway..."):
                self.api.client.gateways.delete(self.api.project, [args.name])
            console.print("Gateway deleted")
        else:
            console.print("Canceled")
            return

    def _update(self, args: argparse.Namespace):
        with console.status("Updating gateway..."):
            if args.set_default:
                self.api.client.gateways.set_default(self.api.project, args.name)
            if args.domain:
                self.api.client.gateways.set_wildcard_domain(
                    self.api.project, args.name, args.domain
                )
        gateway = self.api.client.gateways.get(self.api.project, args.name)
        print_gateways_table([gateway])
