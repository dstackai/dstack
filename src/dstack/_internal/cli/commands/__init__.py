import argparse
import os
from abc import ABC, abstractmethod
from typing import List, Optional

from rich_argparse import RichHelpFormatter

from dstack._internal.cli.services.completion import ProjectNameCompleter
from dstack._internal.cli.utils.common import configure_logging
from dstack.api import Client


class BaseCommand(ABC):
    NAME: str = "name the command"
    DESCRIPTION: str = "describe the command"
    DEFAULT_HELP: bool = True
    ALIASES: Optional[List[str]] = None

    def __init__(self, parser: argparse.ArgumentParser):
        self._parser = parser

    @classmethod
    def register(cls, subparsers):
        parser_kwargs = {}
        if cls.DESCRIPTION:
            parser_kwargs["help"] = cls.DESCRIPTION
        if cls.ALIASES is not None:
            parser_kwargs["aliases"] = cls.ALIASES
        parser: argparse.ArgumentParser = subparsers.add_parser(
            cls.NAME,
            add_help=False,
            formatter_class=RichHelpFormatter,
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
    api: Client

    def _register(self):
        self._parser.add_argument(
            "--project",
            help="The name of the project. Defaults to [code]$DSTACK_PROJECT[/]",
            metavar="NAME",
            default=os.getenv("DSTACK_PROJECT"),
        ).completer = ProjectNameCompleter()  # type: ignore[attr-defined]

    def _command(self, args: argparse.Namespace):
        configure_logging()
        self.api = Client.from_config(project_name=args.project)
