from argparse import Namespace, _SubParsersAction


class BasicCommand(object):
    NAME = "name the command"
    DESCRIPTION = "describe the command"
    SUBCOMMANDS = []

    def __init__(self, parser: _SubParsersAction):
        self._parser = parser.add_parser(self.name, help=self.description, add_help=False)
        self._parser.add_argument(
            "-h",
            "--help",
            action="help",
            help="Show this help message and exit",
        )
        self._parser.set_defaults(func=self._command)

    @property
    def name(self):
        return self.NAME

    @property
    def description(self):
        return self.DESCRIPTION

    def register(self):
        ...

    def _command(self, args: Namespace):
        ...
