import os
from argparse import Namespace

from dstack._internal import settings
from dstack._internal.cli.commands import BaseCommand
from dstack._internal.core.errors import CLIError

UVICORN_INSTALLED = True
try:
    import uvicorn
except ImportError:
    UVICORN_INSTALLED = False


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
            "-y",
            "--yes",
            help="Don't ask for confirmation (e.g. update the config)",
            action="store_true",
        )
        self._parser.add_argument(
            "-n",
            "--no",
            help="Don't ask for confirmation (e.g. do not update the config)",
            action="store_true",
        )
        self._parser.add_argument("--token", type=str, help="The admin user token")

    def _command(self, args: Namespace):
        super()._command(args)

        if not UVICORN_INSTALLED:
            raise CLIError(
                "Failed to start dstack server due to missing server dependencies."
                "\nInstall server dependencies with `pip install dstack[server]` or `pip install dstack[all]`."
            )

        os.environ["DSTACK_SERVER_HOST"] = args.host
        os.environ["DSTACK_SERVER_PORT"] = str(args.port)
        os.environ["DSTACK_SERVER_LOG_LEVEL"] = args.log_level
        if args.yes:
            os.environ["DSTACK_UPDATE_DEFAULT_PROJECT"] = "1"
        if args.no:
            os.environ["DSTACK_DO_NOT_UPDATE_DEFAULT_PROJECT"] = "1"
        if args.token:
            os.environ["DSTACK_SERVER_ADMIN_TOKEN"] = args.token
        uvicorn_log_level = os.getenv("DSTACK_SERVER_UVICORN_LOG_LEVEL", "ERROR").lower()
        reload_disabled = os.getenv("DSTACK_SERVER_RELOAD_DISABLED") is not None

        uvicorn.run(  # type: ignore[unbound-variable]
            "dstack._internal.server.main:app",
            host=args.host,
            port=args.port,
            reload=settings.DSTACK_VERSION is None and not reload_disabled,
            log_level=uvicorn_log_level,
            workers=1,
        )
