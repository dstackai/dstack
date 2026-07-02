import argparse
import time

from rich.table import Table

from dstack._internal.cli.services.configurators.base import BaseApplyConfigurator
from dstack._internal.cli.utils.common import (
    LIVE_TABLE_PROVISION_INTERVAL_SECS,
    confirm_ask,
    console,
)
from dstack._internal.cli.utils.gateway import get_gateways_table
from dstack._internal.cli.utils.rich import MultiItemStatus
from dstack._internal.core.errors import (
    MethodNotAllowedError,
    ResourceNotExistsError,
)
from dstack._internal.core.models.common import ApplyAction
from dstack._internal.core.models.configurations import ApplyConfigurationType
from dstack._internal.core.models.gateways import (
    ApplyGatewayPlanInput,
    Gateway,
    GatewayConfiguration,
    GatewayPlan,
    GatewaySpec,
    GatewayStatus,
)
from dstack._internal.core.services.diff import diff_models
from dstack._internal.utils.common import local_time
from dstack._internal.utils.logging import get_logger
from dstack._internal.utils.nested_list import NestedList, NestedListItem
from dstack.api._public import Client

logger = get_logger(__name__)


class GatewayConfigurator(BaseApplyConfigurator[GatewayConfiguration]):
    TYPE = ApplyConfigurationType.GATEWAY

    def apply_configuration(
        self,
        conf: GatewayConfiguration,
        configuration_path: str,
        command_args: argparse.Namespace,
        configurator_args: argparse.Namespace,
    ):
        self.apply_args(conf, configurator_args)
        spec = GatewaySpec(
            configuration=conf,
            configuration_path=configuration_path,
        )
        if spec.configuration.router is not None:
            logger.warning(
                "Specifying `router` in gateway configurations is deprecated"
                " and will be disallowed in a future release."
                " Please migrate to replica-based routers:"
                " https://dstack.ai/docs/concepts/services/#pd-disaggregation"
            )
        with console.status("Getting apply plan..."):
            try:
                plan = self.api.client.gateways.get_plan(project_name=self.api.project, spec=spec)
                use_legacy_api = False
            except MethodNotAllowedError:
                # pre-0.20.27 server
                plan = _get_plan_legacy(self.api, spec)
                use_legacy_api = True
        _print_plan_header(plan)

        action_message = ""
        confirm_message = ""
        delete_gateway_name = None
        if plan.current_resource is None:
            if plan.effective_spec.configuration.name is not None:
                action_message += f"Gateway [code]{plan.effective_spec.configuration.name}[/] does not exist yet."
            confirm_message += "Create the gateway?"
        else:
            action_message += f"Found gateway [code]{plan.effective_spec.configuration.name}[/]."
            diff = diff_models(
                plan.current_resource.configuration,
                plan.effective_spec.configuration,
            )
            changed_fields = list(diff.keys())
            if (
                plan.current_resource.configuration == plan.effective_spec.configuration
                or changed_fields == ["default"]
            ):
                if command_args.yes and not command_args.force:
                    # --force is required only with --yes,
                    # otherwise we may ask for force apply interactively.
                    console.print(
                        "No configuration changes detected. Use --force to apply anyway."
                    )
                    return
                action_message += " No configuration changes detected."
                confirm_message += "Re-create the gateway?"
                delete_gateway_name = plan.current_resource.name
            else:
                formatted_diff = NestedList(
                    children=[NestedListItem(field) for field in diff]
                ).render()
                if plan.action == ApplyAction.UPDATE:
                    action_message += f" Detected changes that [code]can[/] be updated in-place:\n{formatted_diff}"
                    confirm_message += "Update the gateway?"
                else:
                    action_message += f" Detected changes that [error]cannot[/] be updated in-place:\n{formatted_diff}"
                    confirm_message += "Re-create the gateway?"
                    delete_gateway_name = plan.current_resource.name

        console.print(action_message)
        if not command_args.yes and not confirm_ask(confirm_message):
            console.print("\nExiting...")
            return

        if delete_gateway_name is not None:
            with console.status("Deleting existing gateway..."):
                self.api.client.gateways.delete(
                    project_name=self.api.project,
                    gateways_names=[delete_gateway_name],
                )
                # Gateway deletion is async. Wait for gateway to be deleted.
                while True:
                    try:
                        self.api.client.gateways.get(
                            project_name=self.api.project,
                            gateway_name=delete_gateway_name,
                        )
                    except ResourceNotExistsError:
                        break
                    else:
                        time.sleep(1)

        with console.status("Applying plan..."):
            if use_legacy_api:
                gateway = self.api.client.gateways.create(
                    project_name=self.api.project,
                    configuration=conf,
                )
            else:
                gateway = self.api.client.gateways.apply_plan(
                    project_name=self.api.project,
                    plan=ApplyGatewayPlanInput(
                        spec=spec,
                        current_resource=plan.current_resource,
                    ),
                )

        if plan.action == ApplyAction.UPDATE and delete_gateway_name is None:
            console.print(get_gateways_table([gateway], current_project=self.api.project))
            return

        if command_args.detach:
            console.print("Gateway configuration submitted. Exiting...")
            return
        try:
            with MultiItemStatus(
                f"Provisioning [code]{gateway.name}[/]...", console=console
            ) as live:
                while not _finished_provisioning(gateway):
                    table = get_gateways_table(
                        [gateway], current_project=self.api.project, include_created=True
                    )
                    live.update(table)
                    time.sleep(LIVE_TABLE_PROVISION_INTERVAL_SECS)
                    gateway = self.api.client.gateways.get(self.api.project, gateway.name)
        except KeyboardInterrupt:
            if not command_args.yes and confirm_ask("Delete the gateway before exiting?"):
                with console.status("Deleting gateway..."):
                    self.api.client.gateways.delete(
                        project_name=self.api.project,
                        gateways_names=[gateway.name],
                    )
            else:
                console.print("Exiting... Gateway provisioning will continue in the background.")
            return
        console.print(
            get_gateways_table(
                [gateway],
                current_project=self.api.project,
                verbose=gateway.status == GatewayStatus.FAILED,
                include_created=True,
                format_date=local_time,
            )
        )
        if gateway.status == GatewayStatus.FAILED:
            console.print(
                f"\n[error]Provisioning failed. Error: {gateway.status_message or 'unknown'}[/]"
            )
            exit(1)

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

    @classmethod
    def register_args(cls, parser: argparse.ArgumentParser):
        configuration_group = parser.add_argument_group(f"{cls.TYPE.value} Options")
        configuration_group.add_argument(
            "-n",
            "--name",
            dest="name",
            help="The gateway name",
        )

    def apply_args(self, conf: GatewayConfiguration, args: argparse.Namespace):
        if args.name:
            conf.name = args.name


def _get_plan_legacy(api: Client, spec: GatewaySpec) -> GatewayPlan:
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
        effective_spec=spec,
        current_resource=current_resource,
        action=ApplyAction.CREATE,
    )


def _print_plan_header(plan: GatewayPlan):
    def th(s: str) -> str:
        return f"[bold]{s}[/bold]"

    configuration_table = Table(box=None, show_header=False)
    configuration_table.add_column(no_wrap=True)  # key
    configuration_table.add_column()  # value

    configuration_table.add_row(th("Project"), plan.project_name)
    configuration_table.add_row(th("User"), plan.user)
    configuration_table.add_row(th("Configuration"), plan.effective_spec.configuration_path)
    configuration_table.add_row(th("Type"), plan.effective_spec.configuration.type)

    domain = "-"
    if plan.effective_spec.configuration.domain is not None:
        domain = plan.effective_spec.configuration.domain

    configuration_table.add_row(th("Backend"), plan.effective_spec.configuration.backend.value)
    configuration_table.add_row(th("Region"), plan.effective_spec.configuration.region)
    configuration_table.add_row(th("Domain"), domain)

    if plan.effective_spec.configuration.replicas is not None:
        assert isinstance(plan.effective_spec.configuration.replicas, int)
        configuration_table.add_row(
            th("Replicas"), str(plan.effective_spec.configuration.replicas)
        )

    console.print(configuration_table)
    console.print()


def _finished_provisioning(gateway: Gateway) -> bool:
    return gateway.status in [GatewayStatus.RUNNING, GatewayStatus.FAILED]
