from argparse import Namespace


class BasicCommand(object):
    NAME = "name the command"
    DESCRIPTION = "describe the command"
    SUBCOMMANDS = []

    def __init__(self, parser):
        self._parser = parser.add_parser(self.name, help=self.description)
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
