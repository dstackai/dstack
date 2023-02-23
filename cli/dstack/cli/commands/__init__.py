from argparse import Namespace, _SubParsersAction

from dstack.cli.updates import check_for_updates


class BasicCommand(object):
    NAME = "name the command"
    DESCRIPTION = "describe the command"
    SUBCOMMANDS = []

    def __init__(self, parser: _SubParsersAction):
        kwargs = {}
        if self.description:
            kwargs["help"] = self.description
        self._parser = parser.add_parser(self.name, add_help=False, **kwargs)
        self._parser.add_argument(
            "-h",
            "--help",
            action="help",
            help="Show this help message and exit",
        )
        self._parser.set_defaults(func=self.__command)

    @property
    def name(self):
        return self.NAME

    @property
    def description(self):
        return self.DESCRIPTION

    def register(self):
        ...

    def __command(self, args: Namespace):
        check_for_updates()
        self._command(args)

    def _command(self, args: Namespace):
        ...
