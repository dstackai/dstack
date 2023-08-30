import itertools
from argparse import Namespace
from typing import List

from rich.prompt import Confirm
from rich.table import Table
from rich_argparse import RichHelpFormatter

from dstack._internal.cli.commands import BasicCommand
from dstack._internal.cli.utils.common import add_project_argument, check_init, console
from dstack._internal.cli.utils.config import get_hub_client
from dstack._internal.core.gateway import Gateway
from dstack.api.hub import HubClient


class GatewayCommand(BasicCommand):
    NAME = "gateway"
    DESCRIPTION = "Manage gateways"

    def __init__(self, parser):
        super().__init__(parser)

    def register(self):
        add_project_argument(self._parser)
        subparsers = self._parser.add_subparsers(dest="action", required=True)

        list_parser = subparsers.add_parser(
            "list", help="List gateways", formatter_class=RichHelpFormatter
        )
        add_project_argument(list_parser)
        list_parser.set_defaults(sub_func=self.list_gateways)

        create_parser = subparsers.add_parser(
            "create", help="Create a gateway", formatter_class=RichHelpFormatter
        )
        add_project_argument(create_parser)
        create_parser.add_argument("--backend", choices=["aws", "gcp", "azure"], required=True)
        create_parser.set_defaults(sub_func=self.create_gateway)

        delete_gateway_parser = subparsers.add_parser(
            "delete", help="Delete a gateway", formatter_class=RichHelpFormatter
        )
        add_project_argument(delete_gateway_parser)
        delete_gateway_parser.add_argument(
            "-y", "--yes", action="store_true", help="Don't ask for confirmation"
        )
        delete_gateway_parser.add_argument(
            "instance_name", metavar="NAME", type=str, help="The name of the gateway"
        )
        delete_gateway_parser.set_defaults(sub_func=self.delete_gateway)

    @check_init
    def _command(self, args: Namespace):
        hub_client = get_hub_client(project_name=args.project)
        args.sub_func(hub_client, args)

    def create_gateway(self, hub_client: HubClient, args: Namespace):
        for backend in hub_client.get_gateway_backends():
            if backend.backend != args.backend:
                continue
            region = backend.regions[0]
            print(f"Creating gateway in {region}, it may take some time...")
            gateway = hub_client.create_gateway(backend=args.backend, region=backend.regions[0])
            print_gateways_table([gateway])
            return
        exit(f"No {args.backend} backend is available")

    def list_gateways(self, hub_client: HubClient, args: Namespace):
        gateways = hub_client.list_gateways()
        print_gateways_table(gateways)

    def delete_gateway(self, hub_client: HubClient, args: Namespace):
        gateways = hub_client.list_gateways()
        for gateway in gateways:
            if args.instance_name != gateway.head.instance_name:
                continue
            if args.yes or Confirm.ask(f"[red]Delete the gateway '{args.instance_name}'?[/]"):
                hub_client.delete_gateway(args.instance_name)
                console.print("Gateway is deleted")
            return
        else:
            exit(f"No such gateway '{args.instance_name}'")


def print_gateways_table(gateways: List[Gateway]):
    table = Table(box=None)
    table.add_column("BACKEND")
    table.add_column("REGION")
    table.add_column("NAME")
    table.add_column("ADDRESS")
    table.add_column("DEFAULT")

    gateways = sorted(gateways, key=lambda g: g.backend)
    for backend, backend_gateways in itertools.groupby(gateways, key=lambda g: g.backend):
        for i, gateway in enumerate(backend_gateways):
            table.add_row(
                backend if i == 0 else "",
                gateway.head.region,
                gateway.head.instance_name,
                gateway.head.external_ip,
                "✓" if gateway.default else "",
            )
    console.print(table)
    console.print()
