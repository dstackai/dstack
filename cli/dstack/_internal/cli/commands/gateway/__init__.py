from argparse import Namespace

from rich_argparse import RichHelpFormatter

from dstack._internal.cli.commands import BasicCommand
from dstack._internal.cli.common import add_project_argument, check_init
from dstack._internal.cli.config import get_hub_client
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
            "instance_name", metavar="NAME", type=str, help="The name of the gateway"
        )
        delete_gateway_parser.set_defaults(sub_func=self.delete_gateway)

    @check_init
    def _command(self, args: Namespace):
        hub_client = get_hub_client(project_name=args.project)
        args.sub_func(hub_client, args)

    def create_gateway(self, hub_client: HubClient, args: Namespace):
        print("Provisioning, it may take some time...")
        head = hub_client.create_gateway()
        # todo pretty
        print(head)

    def list_gateways(self, hub_client: HubClient, args: Namespace):
        heads = hub_client.list_gateways()
        # todo pretty
        print(*heads, sep="\n")

    def delete_gateway(self, hub_client: HubClient, args: Namespace):
        # todo implement
        exit("Not implemented")
