import argparse
import time
from typing import List

from rich.live import Live
from rich.table import Table

from dstack._internal.cli.services.configurators.base import BaseApplyConfigurator
from dstack._internal.cli.utils.common import (
    LIVE_TABLE_PROVISION_INTERVAL_SECS,
    LIVE_TABLE_REFRESH_RATE_PER_SEC,
    confirm_ask,
    console,
)
from dstack._internal.cli.utils.volume import get_volumes_table
from dstack._internal.core.errors import ResourceNotExistsError
from dstack._internal.core.models.configurations import ApplyConfigurationType
from dstack._internal.core.models.volumes import (
    Volume,
    VolumeConfiguration,
    VolumePlan,
    VolumeSpec,
    VolumeStatus,
)
from dstack.api._public import Client


class VolumeConfigurator(BaseApplyConfigurator):
    TYPE: ApplyConfigurationType = ApplyConfigurationType.VOLUME

    def apply_configuration(
        self,
        conf: VolumeConfiguration,
        configuration_path: str,
        command_args: argparse.Namespace,
        configurator_args: argparse.Namespace,
        unknown_args: List[str],
    ):
        spec = VolumeSpec(
            configuration=conf,
            configuration_path=configuration_path,
        )
        with console.status("Getting apply plan..."):
            plan = _get_plan(api=self.api, spec=spec)
        _print_plan_header(plan)

        action_message = ""
        confirm_message = ""
        if plan.current_resource is None:
            if plan.spec.configuration.name is not None:
                action_message += (
                    f"Volume [code]{plan.spec.configuration.name}[/] does not exist yet."
                )
            confirm_message += "Create the volume?"
        else:
            action_message += f"Found volume [code]{plan.spec.configuration.name}[/]."
            if plan.current_resource.configuration == plan.spec.configuration:
                if command_args.yes and not command_args.force:
                    # --force is required only with --yes,
                    # otherwise we may ask for force apply interactively.
                    console.print(
                        "No configuration changes detected. Use --force to apply anyway."
                    )
                    return
                action_message += " No configuration changes detected."
                confirm_message += "Re-create the volume?"
            else:
                action_message += " Configuration changes detected."
                confirm_message += "Re-create the volume?"

        console.print(action_message)
        if not command_args.yes and not confirm_ask(confirm_message):
            console.print("\nExiting...")
            return

        if plan.current_resource is not None:
            with console.status("Deleting existing volume..."):
                self.api.client.volumes.delete(
                    project_name=self.api.project, names=[plan.current_resource.name]
                )
                # Volume deletion is async. Wait for volume to be deleted.
                while True:
                    try:
                        self.api.client.volumes.get(
                            project_name=self.api.project, name=plan.current_resource.name
                        )
                    except ResourceNotExistsError:
                        break
                    else:
                        time.sleep(1)

        with console.status("Creating volume..."):
            volume = self.api.client.volumes.create(
                project_name=self.api.project,
                configuration=conf,
            )
        if command_args.detach:
            console.print("Volume configuration submitted. Exiting...")
            return
        console.print()
        try:
            with Live(console=console, refresh_per_second=LIVE_TABLE_REFRESH_RATE_PER_SEC) as live:
                while True:
                    live.update(get_volumes_table([volume], verbose=True))
                    if _finished_provisioning(volume):
                        break
                    time.sleep(LIVE_TABLE_PROVISION_INTERVAL_SECS)
                    volume = self.api.client.volumes.get(self.api.project, volume.name)
        except KeyboardInterrupt:
            if confirm_ask("Delete the volume before exiting?"):
                with console.status("Deleting volume..."):
                    self.api.client.volumes.delete(
                        project_name=self.api.project, names=[volume.name]
                    )
            else:
                console.print("Exiting... Volume provisioning will continue in the background.")

    def delete_configuration(
        self,
        conf: VolumeConfiguration,
        configuration_path: str,
        command_args: argparse.Namespace,
    ):
        if conf.name is None:
            console.print("[error]Configuration specifies no volume to delete[/]")
            exit(1)

        try:
            self.api.client.volumes.get(
                project_name=self.api.project,
                name=conf.name,
            )
        except ResourceNotExistsError:
            console.print(f"Volume [code]{conf.name}[/] does not exist")
            exit(1)

        if not command_args.yes and not confirm_ask(f"Delete the volume [code]{conf.name}[/]?"):
            console.print("\nExiting...")
            return

        with console.status("Deleting volume..."):
            self.api.client.volumes.delete(project_name=self.api.project, names=[conf.name])

        console.print(f"Volume [code]{conf.name}[/] deleted")


def _get_plan(api: Client, spec: VolumeSpec) -> VolumePlan:
    # TODO: Implement server-side /get_plan with an offer included
    user = api.client.users.get_my_user()
    current_resource = None
    if spec.configuration.name is not None:
        try:
            current_resource = api.client.volumes.get(
                project_name=api.project, name=spec.configuration.name
            )
        except ResourceNotExistsError:
            pass
    return VolumePlan(
        project_name=api.project,
        user=user.username,
        spec=spec,
        current_resource=current_resource,
    )


def _print_plan_header(plan: VolumePlan):
    def th(s: str) -> str:
        return f"[bold]{s}[/bold]"

    configuration_table = Table(box=None, show_header=False)
    configuration_table.add_column(no_wrap=True)  # key
    configuration_table.add_column()  # value

    configuration_table.add_row(th("Project"), plan.project_name)
    configuration_table.add_row(th("User"), plan.user)
    configuration_table.add_row(th("Configuration"), plan.spec.configuration_path)
    configuration_table.add_row(th("Type"), plan.spec.configuration.type)

    volume_type = "managed"
    size = "-"
    if plan.spec.configuration.size is not None:
        size = str(plan.spec.configuration.size)
    if plan.spec.configuration.volume_id is not None:
        volume_type = "external"

    configuration_table.add_row(th("Volume type"), volume_type)
    configuration_table.add_row(th("Backend"), plan.spec.configuration.backend.value)
    configuration_table.add_row(th("Region"), plan.spec.configuration.region)
    configuration_table.add_row(th("Size"), size)

    console.print(configuration_table)
    console.print()


def _finished_provisioning(volume: Volume) -> bool:
    return volume.status in [VolumeStatus.ACTIVE, VolumeStatus.FAILED]
