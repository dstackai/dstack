import argparse

from dstack._internal.cli.commands import APIBaseCommand
from dstack._internal.cli.utils.common import confirm_ask, console
from dstack._internal.cli.utils.volume import print_volumes_table
from dstack._internal.core.errors import ResourceNotExistsError


class VolumeCommand(APIBaseCommand):
    NAME = "volume"
    DESCRIPTION = "Manage volumes"

    def _register(self):
        super()._register()
        self._parser.set_defaults(subfunc=self._list)
        subparsers = self._parser.add_subparsers(dest="action")

        list_parser = subparsers.add_parser(
            "list", help="List volumes", formatter_class=self._parser.formatter_class
        )
        list_parser.add_argument(
            "-v", "--verbose", action="store_true", help="Show more information"
        )
        list_parser.set_defaults(subfunc=self._list)

        delete_parser = subparsers.add_parser(
            "delete",
            help="Delete volumes",
            formatter_class=self._parser.formatter_class,
        )
        delete_parser.add_argument(
            "name",
            help="The name of the volume",
        )
        delete_parser.add_argument(
            "-y", "--yes", help="Don't ask for confirmation", action="store_true"
        )
        delete_parser.set_defaults(subfunc=self._delete)

    def _command(self, args: argparse.Namespace):
        super()._command(args)
        args.subfunc(args)

    def _list(self, args: argparse.Namespace):
        volumes = self.api.client.volumes.list(self.api.project)
        print_volumes_table(volumes, verbose=getattr(args, "verbose", False))

    def _delete(self, args: argparse.Namespace):
        try:
            self.api.client.volumes.get(project_name=self.api.project, name=args.name)
        except ResourceNotExistsError:
            console.print(f"Volume [code]{args.name}[/] does not exist")
            return

        if not args.yes and not confirm_ask(f"Delete the volume [code]{args.name}[/]?"):
            console.print("\nExiting...")
            return

        with console.status("Deleting volume..."):
            self.api.client.volumes.delete(project_name=self.api.project, names=[args.name])

        console.print(f"Volume [code]{args.name}[/] deleted")
