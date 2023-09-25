import argparse
from abc import ABC, abstractmethod

import dstack._internal.core.services.api_client as api_client_service
from dstack.api.server import APIClient


class BaseCommand(ABC):
    NAME: str = "name the command"
    DESCRIPTION: str = "describe the command"
    DEFAULT_HELP: bool = True

    def __init__(self, parser: argparse.ArgumentParser):
        self._parser = parser

    @classmethod
    def register(cls, subparsers):
        parser_kwargs = {}
        if cls.DESCRIPTION:
            parser_kwargs["help"] = cls.DESCRIPTION
        parser: argparse.ArgumentParser = subparsers.add_parser(
            cls.NAME,
            add_help=False,
            # todo Rich
            **parser_kwargs,
        )
        command = cls(parser)
        if cls.DEFAULT_HELP:
            parser.add_argument(
                "-h",
                "--help",
                help="Show this help message and exit",
                action="help",
                default=argparse.SUPPRESS,
            )
        command._register()
        parser.set_defaults(func=command._command)

    @abstractmethod
    def _register(self):
        pass

    @abstractmethod
    def _command(self, args: argparse.Namespace):
        pass


class APIBaseCommand(BaseCommand):
    api_client: APIClient = None
    project_name: str = None

    def _register(self):
        self._parser.add_argument("--project")  # TODO env var default

    def _command(self, args: argparse.Namespace):
        self.api_client, self.project_name = api_client_service.get_api_client(args.project)
