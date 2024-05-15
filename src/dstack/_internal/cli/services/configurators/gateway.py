import argparse

from dstack._internal.cli.services.configurators.base import BaseApplyConfigurator
from dstack._internal.cli.utils.common import confirm_ask, console
from dstack._internal.cli.utils.gateway import print_gateways_table
from dstack._internal.core.errors import ResourceNotExistsError
from dstack._internal.core.models.configurations import ApplyConfigurationType
from dstack._internal.core.models.gateways import GatewayConfiguration


class GatewayConfigurator(BaseApplyConfigurator):
    TYPE: ApplyConfigurationType = ApplyConfigurationType.GATEWAY

    def apply_configuration(self, conf: GatewayConfiguration, args: argparse.Namespace):
        confirmed = False
        if conf.name is not None:
            try:
                self.api_client.client.gateways.get(
                    project_name=self.api_client.project, gateway_name=conf.name
                )
            except ResourceNotExistsError:
                pass
            else:
                if not args.yes and not confirm_ask(
                    f"Gateway [code]{conf.name}[/] already exist. Re-create the gateway?"
                ):
                    console.print("\nExiting...")
                    return
                confirmed = True
                with console.status("Deleting gateway..."):
                    self.api_client.client.gateways.delete(
                        project_name=self.api_client.project, gateways_names=[conf.name]
                    )
        if not confirmed and not args.yes:
            if not confirm_ask(
                f"Gateway [code]{conf.name}[/] does not exist yet. Create the gateway?"
            ):
                console.print("\nExiting...")
                return
        with console.status("Creating gateway..."):
            gateway = self.api_client.client.gateways.create(
                project_name=self.api_client.project,
                configuration=conf,
            )
        print_gateways_table([gateway])
