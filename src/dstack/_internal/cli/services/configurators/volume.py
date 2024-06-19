import argparse

from dstack._internal.cli.services.configurators.base import BaseApplyConfigurator
from dstack._internal.cli.utils.common import confirm_ask, console
from dstack._internal.cli.utils.volume import print_volumes_table
from dstack._internal.core.errors import ResourceNotExistsError
from dstack._internal.core.models.configurations import ApplyConfigurationType
from dstack._internal.core.models.volumes import VolumeConfiguration


class VolumeConfigurator(BaseApplyConfigurator):
    TYPE: ApplyConfigurationType = ApplyConfigurationType.VOLUME

    def apply_configuration(self, conf: VolumeConfiguration, args: argparse.Namespace):
        # TODO: Show apply plan
        confirmed = False
        if conf.name is not None:
            try:
                volume = self.api_client.client.volumes.get(
                    project_name=self.api_client.project,
                    name=conf.name,
                )
            except ResourceNotExistsError:
                pass
            else:
                if volume.configuration == conf:
                    if not args.force:
                        console.print(
                            "Volume configuration has not changed. Use --force to recreate the volume."
                        )
                        return
                    if not args.yes and not confirm_ask(
                        "Volume configuration has not changed. Re-create the volume?"
                    ):
                        console.print("\nExiting...")
                        return
                elif not args.yes and not confirm_ask(
                    f"Volume [code]{conf.name}[/] already exists. Re-create the volume?"
                ):
                    console.print("\nExiting...")
                    return
                confirmed = True
                with console.status("Deleting volume..."):
                    self.api_client.client.volumes.delete(
                        project_name=self.api_client.project, names=[conf.name]
                    )
        if not confirmed and not args.yes:
            if not confirm_ask(
                f"Volume [code]{conf.name}[/] does not exist yet. Create the volume?"
            ):
                console.print("\nExiting...")
                return
        with console.status("Creating volume..."):
            volume = self.api_client.client.volumes.create(
                project_name=self.api_client.project,
                configuration=conf,
            )
        print_volumes_table([volume])

    def delete_configuration(self, conf: VolumeConfiguration, args: argparse.Namespace):
        if conf.name is None:
            console.print("[error]Configuration specifies no volume to delete[/]")
            return

        try:
            self.api_client.client.volumes.get(
                project_name=self.api_client.project,
                name=conf.name,
            )
        except ResourceNotExistsError:
            console.print(f"Volume [code]{conf.name}[/] does not exist")
            return

        if not args.yes and not confirm_ask(f"Delete the volume [code]{conf.name}[/]?"):
            console.print("\nExiting...")
            return

        with console.status("Deleting volume..."):
            self.api_client.client.volumes.delete(
                project_name=self.api_client.project, names=[conf.name]
            )

        console.print(f"Volume [code]{conf.name}[/] deleted")
