import os
from argparse import Namespace

import uvicorn

from dstack import version
from dstack._internal.cli.commands import BaseCommand


class ServerCommand(BaseCommand):
    NAME = "server"
    DESCRIPTION = "Start a server"

    def _register(self):
        super()._register()

        self._parser.add_argument(
            "--host",
            type=str,
            help="Bind socket to this host. Defaults to 127.0.0.1",
            default=os.getenv("DSTACK_SERVER_HOST", "127.0.0.1"),
        )
        self._parser.add_argument(
            "-p",
            "--port",
            type=int,
            help="Bind socket to this port. Defaults to 3000.",
            default=os.getenv("DSTACK_SERVER_PORT", 3000),
        )
        self._parser.add_argument(
            "-l",
            "--log-level",
            type=str,
            help="Server logging level. Defaults to INFO.",
            default=os.getenv("DSTACK_SERVER_LOG_LEVEL", "INFO"),
        )
        self._parser.add_argument(
            "--default",
            help="Update the default project configuration",
            action="store_true",
        )
        self._parser.add_argument(
            "--no-default",
            help="Do not update the default project configuration",
            action="store_true",
        )
        self._parser.add_argument("--token", type=str, help="The admin user token")

    def _command(self, args: Namespace):
        super()._command(args)

        os.environ["DSTACK_SERVER_HOST"] = args.host
        os.environ["DSTACK_SERVER_PORT"] = str(args.port)
        os.environ["DSTACK_SERVER_LOG_LEVEL"] = args.log_level
        if args.default:
            os.environ["DSTACK_UPDATE_DEFAULT_PROJECT"] = "1"
        if args.no_default:
            os.environ["DSTACK_DO_NOT_UPDATE_DEFAULT_PROJECT"] = "1"
        if args.token:
            os.environ["DSTACK_SERVER_ADMIN_TOKEN"] = args.token
        uvicorn_log_level = os.getenv("DSTACK_SERVER_UVICORN_LOG_LEVEL", "ERROR").lower()
        uvicorn.run(
            "dstack._internal.server.main:app",
            host=args.host,
            port=args.port,
            reload=version.__version__ is None,
            log_level=uvicorn_log_level,
        )
