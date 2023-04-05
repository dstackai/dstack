import os
from argparse import Namespace

import uvicorn
from rich_argparse import RichHelpFormatter

from dstack import version
from dstack.cli.commands import BasicCommand


class HubCommand(BasicCommand):
    NAME = "hub"
    DESCRIPTION = None  # Hidden by default

    def __init__(self, parser):
        super(HubCommand, self).__init__(parser)

    def _hub_start(self, args: Namespace):
        os.environ["DSTACK_HUB_HOST"] = args.host
        os.environ["DSTACK_HUB_PORT"] = str(args.port)
        os.environ["DSTACK_HUB_LOG_LEVEL"] = args.log_level
        if args.token:
            os.environ["DSTACK_HUB_ADMIN_TOKEN"] = args.token
        uvicorn.run(
            "dstack.hub.main:app",
            host=args.host,
            port=args.port,
            reload=version.__version__ is None,
            log_level="error",
        )

    def register(self):
        subparsers = self._parser.add_subparsers()
        hub_parser = subparsers.add_parser(
            "start",
            help="Start a hub server",
            formatter_class=RichHelpFormatter,
            add_help=False,
        )
        hub_parser.add_argument(
            "-h",
            "--help",
            action="help",
            help="Show this help message and exit",
        )
        hub_parser.add_argument(
            "--host",
            metavar="HOST",
            type=str,
            help="Bind socket to this host. Defaults to 127.0.0.1",
            default="127.0.0.1",
        )
        hub_parser.add_argument(
            "-p",
            "--port",
            metavar="PORT",
            type=int,
            help="Bind socket to this port. Defaults to 3000.",
            default=3000,
        )
        hub_parser.add_argument(
            "-l",
            "--log-level",
            metavar="LOG-LEVEL",
            type=str,
            help="",
            default="ERROR",
        )
        hub_parser.add_argument("--token", metavar="TOKEN", type=str, help="The admin user token")
        hub_parser.set_defaults(func=self._hub_start)

    def _command(self, args: Namespace):
        self._parser.print_help()
