import argparse

from dstack._internal.cli.commands import APIBaseCommand
from dstack._internal.cli.utils.common import confirm_ask, console
from dstack._internal.cli.utils.fleet import print_fleets_table
from dstack._internal.core.errors import ResourceNotExistsError


class FleetCommand(APIBaseCommand):
    NAME = "fleet"
    DESCRIPTION = "Manage fleets"

    def _register(self):
        super()._register()
        self._parser.set_defaults(subfunc=self._list)
        subparsers = self._parser.add_subparsers(dest="action")

        list_parser = subparsers.add_parser(
            "list", help="List fleets", formatter_class=self._parser.formatter_class
        )
        list_parser.add_argument(
            "-v", "--verbose", action="store_true", help="Show more information"
        )
        list_parser.set_defaults(subfunc=self._list)

        rm_parser = subparsers.add_parser(
            "rm", help="Delete fleets and instances", formatter_class=self._parser.formatter_class
        )
        rm_parser.add_argument(
            "name",
            help="The name of the fleet",
        )
        rm_parser.add_argument(
            "-i",
            "--instance",
            action="append",
            metavar="INSTANCE",
            dest="instances",
            help="The instance to delete",
            type=int,
        )
        rm_parser.add_argument(
            "-y", "--yes", help="Don't ask for confirmation", action="store_true"
        )
        rm_parser.set_defaults(subfunc=self._rm)

    def _command(self, args: argparse.Namespace):
        super()._command(args)
        args.subfunc(args)

    def _list(self, args: argparse.Namespace):
        fleets = self.api.client.fleets.list(self.api.project)
        print_fleets_table(fleets, verbose=getattr(args, "verbose", False))

    def _rm(self, args: argparse.Namespace):
        try:
            self.api.client.fleets.get(project_name=self.api.project, name=args.name)
        except ResourceNotExistsError:
            console.print(f"Fleet [code]{args.name}[/] does not exist")
            return

        if len(args.instances) == 0:
            if not args.yes and not confirm_ask(f"Delete the fleet [code]{args.name}[/]?"):
                console.print("\nExiting...")
                return

            with console.status("Deleting fleet..."):
                self.api.client.fleets.delete(project_name=self.api.project, names=[args.name])

            console.print(f"Fleet [code]{args.name}[/] deleted")
            return

        if not args.yes and not confirm_ask(
            f"Delete the fleet [code]{args.name}[/] instances [code]{args.instances}[/]?"
        ):
            console.print("\nExiting...")
            return

        with console.status("Deleting fleet instances..."):
            self.api.client.fleets.delete_instances(
                project_name=self.api.project, name=args.name, instance_nums=args.instances
            )

        console.print(f"Fleet [code]{args.name}[/] instances deleted")
