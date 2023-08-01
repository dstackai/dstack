from argparse import Namespace
from typing import List

from rich.prompt import Confirm
from rich.table import Table
from rich_argparse import RichHelpFormatter

from dstack._internal.cli.commands import BasicCommand
from dstack._internal.cli.utils.common import add_project_argument, check_init, console
from dstack._internal.cli.utils.config import get_hub_client
from dstack._internal.core.gateway import GatewayHead
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
        print("Creating gateway, it may take some time...")
        head = hub_client.create_gateway()
        print_gateways_table([head])

    def list_gateways(self, hub_client: HubClient, args: Namespace):
        heads = hub_client.list_gateways()
        print_gateways_table(heads)

    def delete_gateway(self, hub_client: HubClient, args: Namespace):
        heads = hub_client.list_gateways()
        if args.instance_name not in [head.instance_name for head in heads]:
            exit(f"No such gateway '{args.instance_name}'")
        if args.yes or Confirm.ask(f"[red]Delete the gateway '{args.instance_name}'?[/]"):
            hub_client.delete_gateway(args.instance_name)
            console.print("Gateway is deleted")
            exit(0)


def print_gateways_table(heads: List[GatewayHead]):
    table = Table(box=None)
    table.add_column("NAME")
    table.add_column("ADDRESS")
    for head in heads:
        table.add_row(
            head.instance_name,
            head.external_ip,
        )
    console.print(table)
    console.print()
