import argparse
from pathlib import Path

from dstack._internal.cli.services.configurators.base import BaseApplyConfigurator
from dstack._internal.cli.utils.common import confirm_ask, console
from dstack._internal.cli.utils.fleet import print_fleets_table
from dstack._internal.core.errors import ResourceNotExistsError
from dstack._internal.core.models.configurations import ApplyConfigurationType
from dstack._internal.core.models.fleets import FleetConfiguration, FleetSpec
from dstack.api.utils import load_profile


class FleetConfigurator(BaseApplyConfigurator):
    TYPE: ApplyConfigurationType = ApplyConfigurationType.FLEET

    def apply_configuration(self, conf: FleetConfiguration, args: argparse.Namespace):
        profile = load_profile(Path.cwd(), None)
        spec = FleetSpec(
            configuration=conf,
            profile=profile,
        )
        confirmed = False
        if conf.name is not None:
            try:
                fleet = self.api_client.client.fleets.get(
                    project_name=self.api_client.project,
                    name=conf.name,
                )
            except ResourceNotExistsError:
                pass
            else:
                if fleet.spec.configuration == conf:
                    if not args.force:
                        console.print(
                            "Fleet configuration has not changed. Use --force to recreate the fleet."
                        )
                        return
                    if not args.yes and not confirm_ask(
                        "Fleet configuration has not changed. Re-create the fleet?"
                    ):
                        console.print("\nExiting...")
                        return
                elif not args.yes and not confirm_ask(
                    f"Fleet [code]{conf.name}[/] already exists. Re-create the fleet?"
                ):
                    console.print("\nExiting...")
                    return
                confirmed = True
                with console.status("Deleting fleet..."):
                    self.api_client.client.fleets.delete(
                        project_name=self.api_client.project, names=[conf.name]
                    )
        if not confirmed and not args.yes:
            if not confirm_ask(
                f"Fleet [code]{conf.name}[/] does not exist yet. Create the fleet?"
            ):
                console.print("\nExiting...")
                return
        with console.status("Creating fleet..."):
            fleet = self.api_client.client.fleets.create(
                project_name=self.api_client.project,
                spec=spec,
            )
        print_fleets_table([fleet])

    def delete_configuration(self, conf: FleetConfiguration, args: argparse.Namespace):
        if conf.name is None:
            console.print("[error]Configuration specifies no fleet to delete[/]")
            return

        try:
            self.api_client.client.fleets.get(
                project_name=self.api_client.project,
                name=conf.name,
            )
        except ResourceNotExistsError:
            console.print(f"Fleet [code]{conf.name}[/] does not exist")
            return

        if not args.yes and not confirm_ask(f"Delete the fleet [code]{conf.name}[/]?"):
            console.print("\nExiting...")
            return

        with console.status("Deleting fleet..."):
            self.api_client.client.fleets.delete(
                project_name=self.api_client.project, names=[conf.name]
            )

        console.print(f"Fleet [code]{conf.name}[/] deleted")
