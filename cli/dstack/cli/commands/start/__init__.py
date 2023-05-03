import os
from argparse import Namespace

import uvicorn

from dstack import version
from dstack.cli.commands import BasicCommand


class StartCommand(BasicCommand):
    NAME = "start"
    DESCRIPTION = "Start a hub server"

    def __init__(self, parser):
        super(StartCommand, self).__init__(parser)

    def _command(self, args: Namespace):
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
        self._parser.add_argument(
            "--host",
            type=str,
            help="Bind socket to this host. Defaults to 127.0.0.1",
            default=os.getenv("DSTACK_HUB_HOST", "127.0.0.1"),
        )
        self._parser.add_argument(
            "-p",
            "--port",
            type=int,
            help="Bind socket to this port. Defaults to 3000.",
            default=os.getenv("DSTACK_HUB_PORT", 3000),
        )
        self._parser.add_argument(
            "-l",
            "--log-level",
            type=str,
            help="Logging level for hub. Defaults to ERROR.",
            default=os.getenv("DSTACK_HUB_LOG_LEVEL", "ERROR"),
        )
        self._parser.add_argument("--token", type=str, help="The admin user token")
