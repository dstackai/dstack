import argparse
from typing import List

from dstack._internal.cli.services.configurators.base import BaseApplyConfigurator
from dstack._internal.cli.utils.common import confirm_ask, console
from dstack._internal.cli.utils.gateway import print_gateways_table
from dstack._internal.core.errors import ResourceNotExistsError
from dstack._internal.core.models.configurations import ApplyConfigurationType
from dstack._internal.core.models.gateways import GatewayConfiguration


class GatewayConfigurator(BaseApplyConfigurator):
    TYPE: ApplyConfigurationType = ApplyConfigurationType.GATEWAY

    def apply_configuration(
        self,
        conf: GatewayConfiguration,
        configuration_path: str,
        command_args: argparse.Namespace,
        configurator_args: argparse.Namespace,
        unknown_args: List[str],
    ):
        # TODO: Show apply plan
        # TODO: Update gateway in-place when domain/default change
        confirmed = False
        if conf.name is not None:
            try:
                gateway = self.api.client.gateways.get(
                    project_name=self.api.project, gateway_name=conf.name
                )
            except ResourceNotExistsError:
                pass
            else:
                if gateway.configuration == conf:
                    if not command_args.force:
                        console.print(
                            "Gateway configuration has not changed. Use --force to recreate the gateway."
                        )
                        return
                    if not command_args.yes and not confirm_ask(
                        "Gateway configuration has not changed. Re-create the gateway?"
                    ):
                        console.print("\nExiting...")
                        return
                elif not command_args.yes and not confirm_ask(
                    f"Gateway [code]{conf.name}[/] already exists. Re-create the gateway?"
                ):
                    console.print("\nExiting...")
                    return
                confirmed = True
                with console.status("Deleting gateway..."):
                    self.api.client.gateways.delete(
                        project_name=self.api.project, gateways_names=[conf.name]
                    )
        if not confirmed and not command_args.yes:
            confirm_message = (
                "Configuration does not specify the gateway name. Create a new gateway?"
            )
            if conf.name is not None:
                confirm_message = (
                    f"Gateway [code]{conf.name}[/] does not exist yet. Create the gateway?"
                )
            if not confirm_ask(confirm_message):
                console.print("\nExiting...")
                return
        with console.status("Creating gateway..."):
            gateway = self.api.client.gateways.create(
                project_name=self.api.project,
                configuration=conf,
            )
        print_gateways_table([gateway])

    def delete_configuration(
        self,
        conf: GatewayConfiguration,
        configuration_path: str,
        command_args: argparse.Namespace,
    ):
        if conf.name is None:
            console.print("[error]Configuration specifies no gateway to delete[/]")
            exit(1)

        try:
            self.api.client.gateways.get(project_name=self.api.project, gateway_name=conf.name)
        except ResourceNotExistsError:
            console.print(f"Gateway [code]{conf.name}[/] does not exist")
            exit(1)

        if not command_args.yes and not confirm_ask(f"Delete the gateway [code]{conf.name}[/]?"):
            console.print("\nExiting...")
            return

        with console.status("Deleting gateway..."):
            self.api.client.gateways.delete(
                project_name=self.api.project, gateways_names=[conf.name]
            )

        console.print(f"Gateway [code]{conf.name}[/] deleted")
