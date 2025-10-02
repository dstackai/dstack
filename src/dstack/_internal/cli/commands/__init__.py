import argparse
import os
import shlex
from abc import ABC, abstractmethod
from typing import ClassVar, Optional

from rich_argparse import RichHelpFormatter

from dstack._internal.cli.services.completion import ProjectNameCompleter
from dstack._internal.cli.utils.common import configure_logging
from dstack._internal.core.errors import CLIError
from dstack.api import Client


class BaseCommand(ABC):
    NAME: ClassVar[str] = "name the command"
    DESCRIPTION: ClassVar[str] = "describe the command"
    DEFAULT_HELP: ClassVar[bool] = True
    ALIASES: ClassVar[Optional[list[str]]] = None
    ACCEPT_EXTRA_ARGS: ClassVar[bool] = False

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
        self._configure_logging()
        if not self.ACCEPT_EXTRA_ARGS and args.extra_args:
            raise CLIError(f"Unrecognized arguments: {shlex.join(args.extra_args)}")

    def _configure_logging(self) -> None:
        """
        Override this method to configure command-specific logging
        """
        configure_logging()


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
        super()._command(args)
        self.api = Client.from_config(project_name=args.project)
