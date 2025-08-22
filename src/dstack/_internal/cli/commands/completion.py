import argcomplete

from dstack._internal.cli.commands import BaseCommand


class CompletionCommand(BaseCommand):
    NAME = "completion"
    DESCRIPTION = "Generate shell completion scripts"

    def _register(self):
        super()._register()
        self._parser.add_argument(
            "shell",
            help="The shell to generate the completion script for",
            choices=["bash", "zsh"],
        )

    def _command(self, args):
        super()._command(args)
        print(argcomplete.shellcode(["dstack"], shell=args.shell))  # type: ignore[attr-defined]
