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
from dstack._internal.cli.utils.gateway import get_gateways_table
from dstack._internal.core.errors import ResourceNotExistsError
from dstack._internal.core.models.configurations import ApplyConfigurationType
from dstack._internal.core.models.gateways import (
    Gateway,
    GatewayConfiguration,
    GatewayPlan,
    GatewaySpec,
    GatewayStatus,
)
from dstack.api._public import Client


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
        spec = GatewaySpec(
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
                    f"Gateway [code]{plan.spec.configuration.name}[/] does not exist yet."
                )
            confirm_message += "Create the gateway?"
        else:
            action_message += f"Found gateway [code]{plan.spec.configuration.name}[/]."
            if plan.current_resource.configuration == plan.spec.configuration:
                if command_args.yes and not command_args.force:
                    # --force is required only with --yes,
                    # otherwise we may ask for force apply interactively.
                    console.print(
                        "No configuration changes detected. Use --force to apply anyway."
                    )
                    return
                action_message += " No configuration changes detected."
                confirm_message += "Re-create the gateway?"
            else:
                action_message += " Configuration changes detected."
                confirm_message += "Re-create the gateway?"

        console.print(action_message)
        if not command_args.yes and not confirm_ask(confirm_message):
            console.print("\nExiting...")
            return

        if plan.current_resource is not None:
            with console.status("Deleting existing gateway..."):
                self.api.client.gateways.delete(
                    project_name=self.api.project,
                    gateways_names=[plan.current_resource.name],
                )
                # Gateway deletion is async. Wait for gateway to be deleted.
                while True:
                    try:
                        self.api.client.gateways.get(
                            project_name=self.api.project,
                            gateway_name=plan.current_resource.name,
                        )
                    except ResourceNotExistsError:
                        break
                    else:
                        time.sleep(1)

        with console.status("Creating gateway..."):
            gateway = self.api.client.gateways.create(
                project_name=self.api.project,
                configuration=conf,
            )
        if command_args.detach:
            console.print("Gateway configuration submitted. Exiting...")
            return
        console.print()
        try:
            with Live(console=console, refresh_per_second=LIVE_TABLE_REFRESH_RATE_PER_SEC) as live:
                while True:
                    live.update(get_gateways_table([gateway], verbose=True))
                    if _finished_provisioning(gateway):
                        break
                    time.sleep(LIVE_TABLE_PROVISION_INTERVAL_SECS)
                    gateway = self.api.client.gateways.get(self.api.project, gateway.name)
        except KeyboardInterrupt:
            if confirm_ask("Delete the gateway before exiting?"):
                with console.status("Deleting gateway..."):
                    self.api.client.gateways.delete(
                        project_name=self.api.project,
                        gateways_names=[gateway.name],
                    )
            else:
                console.print("Exiting... Gateway provisioning will continue in the background.")

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


def _get_plan(api: Client, spec: GatewaySpec) -> GatewayPlan:
    # TODO: Implement server-side /get_plan with an offer included
    user = api.client.users.get_my_user()
    current_resource = None
    if spec.configuration.name is not None:
        try:
            current_resource = api.client.gateways.get(
                project_name=api.project,
                gateway_name=spec.configuration.name,
            )
        except ResourceNotExistsError:
            pass
    return GatewayPlan(
        project_name=api.project,
        user=user.username,
        spec=spec,
        current_resource=current_resource,
    )


def _print_plan_header(plan: GatewayPlan):
    def th(s: str) -> str:
        return f"[bold]{s}[/bold]"

    configuration_table = Table(box=None, show_header=False)
    configuration_table.add_column(no_wrap=True)  # key
    configuration_table.add_column()  # value

    configuration_table.add_row(th("Project"), plan.project_name)
    configuration_table.add_row(th("User"), plan.user)
    configuration_table.add_row(th("Configuration"), plan.spec.configuration_path)
    configuration_table.add_row(th("Type"), plan.spec.configuration.type)

    domain = "-"
    if plan.spec.configuration.domain is not None:
        domain = plan.spec.configuration.domain

    configuration_table.add_row(th("Backend"), plan.spec.configuration.backend.value)
    configuration_table.add_row(th("Region"), plan.spec.configuration.region)
    configuration_table.add_row(th("Domain"), domain)

    console.print(configuration_table)
    console.print()


def _finished_provisioning(gateway: Gateway) -> bool:
    return gateway.status in [GatewayStatus.RUNNING, GatewayStatus.FAILED]
