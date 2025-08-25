import argparse
import time
from pathlib import Path
from typing import List, Optional

from rich.table import Table

from dstack._internal.cli.services.configurators.base import (
    ApplyEnvVarsConfiguratorMixin,
    BaseApplyConfigurator,
)
from dstack._internal.cli.utils.common import (
    LIVE_TABLE_PROVISION_INTERVAL_SECS,
    NO_OFFERS_WARNING,
    confirm_ask,
    console,
)
from dstack._internal.cli.utils.fleet import get_fleets_table
from dstack._internal.cli.utils.rich import MultiItemStatus
from dstack._internal.core.errors import (
    CLIError,
    ConfigurationError,
    MethodNotAllowedError,
    ResourceNotExistsError,
    ServerClientError,
    URLNotFoundError,
)
from dstack._internal.core.models.common import ApplyAction
from dstack._internal.core.models.configurations import ApplyConfigurationType
from dstack._internal.core.models.fleets import (
    Fleet,
    FleetConfiguration,
    FleetPlan,
    FleetSpec,
    InstanceGroupPlacement,
)
from dstack._internal.core.models.instances import InstanceAvailability, InstanceStatus, SSHKey
from dstack._internal.core.services.diff import diff_models
from dstack._internal.utils.common import local_time
from dstack._internal.utils.logging import get_logger
from dstack._internal.utils.ssh import convert_ssh_key_to_pem, generate_public_key, pkey_from_str
from dstack.api._public import Client
from dstack.api.utils import load_profile

logger = get_logger(__name__)


class FleetConfigurator(ApplyEnvVarsConfiguratorMixin, BaseApplyConfigurator[FleetConfiguration]):
    TYPE: ApplyConfigurationType = ApplyConfigurationType.FLEET

    def apply_configuration(
        self,
        conf: FleetConfiguration,
        configuration_path: str,
        command_args: argparse.Namespace,
        configurator_args: argparse.Namespace,
        unknown_args: List[str],
    ):
        self.apply_args(conf, configurator_args, unknown_args)
        profile = load_profile(Path.cwd(), None)
        spec = FleetSpec(
            configuration=conf,
            configuration_path=configuration_path,
            profile=profile,
        )
        _preprocess_spec(spec)

        with console.status("Getting apply plan..."):
            plan = self.api.client.fleets.get_plan(
                project_name=self.api.project,
                spec=spec,
            )
        _print_plan_header(plan)
        if plan.action is not None:
            self._apply_plan(plan, command_args)
        else:
            # Old servers don't support spec update
            self._apply_plan_on_old_server(plan, command_args)

    def _apply_plan(self, plan: FleetPlan, command_args: argparse.Namespace):
        delete_fleet_name: Optional[str] = None
        action_message = ""
        confirm_message = ""
        if plan.current_resource is None:
            if plan.spec.configuration.name is not None:
                action_message += (
                    f"Fleet [code]{plan.spec.configuration.name}[/] does not exist yet."
                )
            confirm_message += "Create the fleet?"
        else:
            action_message += f"Found fleet [code]{plan.spec.configuration.name}[/]."
            if plan.action == ApplyAction.CREATE:
                delete_fleet_name = plan.current_resource.name
                action_message += (
                    " Configuration changes detected. Cannot update the fleet in-place"
                )
                confirm_message += "Re-create the fleet?"
            elif plan.current_resource.spec == plan.effective_spec:
                if command_args.yes and not command_args.force:
                    # --force is required only with --yes,
                    # otherwise we may ask for force apply interactively.
                    console.print(
                        "No configuration changes detected. Use --force to apply anyway."
                    )
                    return
                delete_fleet_name = plan.current_resource.name
                action_message += " No configuration changes detected."
                confirm_message += "Re-create the fleet?"
            else:
                action_message += " Configuration changes detected."
                confirm_message += "Update the fleet in-place?"

        console.print(action_message)
        if not command_args.yes and not confirm_ask(confirm_message):
            console.print("\nExiting...")
            return

        if delete_fleet_name is not None:
            with console.status("Deleting existing fleet..."):
                self.api.client.fleets.delete(
                    project_name=self.api.project, names=[delete_fleet_name]
                )
                # Fleet deletion is async. Wait for fleet to be deleted.
                while True:
                    try:
                        self.api.client.fleets.get(
                            project_name=self.api.project, name=delete_fleet_name
                        )
                    except ResourceNotExistsError:
                        break
                    else:
                        time.sleep(1)

        try:
            with console.status("Applying plan..."):
                fleet = self.api.client.fleets.apply_plan(project_name=self.api.project, plan=plan)
        except ServerClientError as e:
            raise CLIError(e.msg)
        if command_args.detach:
            console.print("Fleet configuration submitted. Exiting...")
            return
        try:
            with MultiItemStatus(
                f"Provisioning [code]{fleet.name}[/]...", console=console
            ) as live:
                while not _finished_provisioning(fleet):
                    table = get_fleets_table([fleet])
                    live.update(table)
                    time.sleep(LIVE_TABLE_PROVISION_INTERVAL_SECS)
                    fleet = self.api.client.fleets.get(self.api.project, fleet.name)
        except KeyboardInterrupt:
            if not command_args.yes and confirm_ask("Delete the fleet before exiting?"):
                with console.status("Deleting fleet..."):
                    self.api.client.fleets.delete(
                        project_name=self.api.project, names=[fleet.name]
                    )
            else:
                console.print("Exiting... Fleet provisioning will continue in the background.")
            return
        console.print(
            get_fleets_table(
                [fleet],
                verbose=_failed_provisioning(fleet),
                format_date=local_time,
            )
        )
        if _failed_provisioning(fleet):
            console.print("\n[error]Some instances failed. Check the table above for errors.[/]")
            exit(1)

    def _apply_plan_on_old_server(self, plan: FleetPlan, command_args: argparse.Namespace):
        action_message = ""
        confirm_message = ""
        if plan.current_resource is None:
            if plan.spec.configuration.name is not None:
                action_message += (
                    f"Fleet [code]{plan.spec.configuration.name}[/] does not exist yet."
                )
            confirm_message += "Create the fleet?"
        else:
            action_message += f"Found fleet [code]{plan.spec.configuration.name}[/]."
            diff = diff_models(
                old=plan.current_resource.spec.configuration,
                new=plan.spec.configuration,
                reset={
                    "ssh_config": {
                        "ssh_key": True,
                        "proxy_jump": {"ssh_key"},
                        "hosts": {"__all__": {"ssh_key": True, "proxy_jump": {"ssh_key"}}},
                    }
                },
            )
            if not diff:
                if command_args.yes and not command_args.force:
                    # --force is required only with --yes,
                    # otherwise we may ask for force apply interactively.
                    console.print(
                        "No configuration changes detected. Use --force to apply anyway."
                    )
                    return
                action_message += " No configuration changes detected."
                confirm_message += "Re-create the fleet?"
            else:
                action_message += " Configuration changes detected."
                confirm_message += "Re-create the fleet?"

        console.print(action_message)
        if not command_args.yes and not confirm_ask(confirm_message):
            console.print("\nExiting...")
            return

        if plan.current_resource is not None:
            with console.status("Deleting existing fleet..."):
                self.api.client.fleets.delete(
                    project_name=self.api.project, names=[plan.current_resource.name]
                )
                # Fleet deletion is async. Wait for fleet to be deleted.
                while True:
                    try:
                        self.api.client.fleets.get(
                            project_name=self.api.project, name=plan.current_resource.name
                        )
                    except ResourceNotExistsError:
                        break
                    else:
                        time.sleep(1)

        try:
            with console.status("Applying plan..."):
                fleet = _apply_plan(self.api, plan)
        except ServerClientError as e:
            raise CLIError(e.msg)
        if command_args.detach:
            console.print("Fleet configuration submitted. Exiting...")
            return
        try:
            with MultiItemStatus(
                f"Provisioning [code]{fleet.name}[/]...", console=console
            ) as live:
                while not _finished_provisioning(fleet):
                    table = get_fleets_table([fleet])
                    live.update(table)
                    time.sleep(LIVE_TABLE_PROVISION_INTERVAL_SECS)
                    fleet = self.api.client.fleets.get(self.api.project, fleet.name)
        except KeyboardInterrupt:
            if confirm_ask("Delete the fleet before exiting?"):
                with console.status("Deleting fleet..."):
                    self.api.client.fleets.delete(
                        project_name=self.api.project, names=[fleet.name]
                    )
            else:
                console.print("Exiting... Fleet provisioning will continue in the background.")
            return
        console.print(
            get_fleets_table(
                [fleet],
                verbose=_failed_provisioning(fleet),
                format_date=local_time,
            )
        )
        if _failed_provisioning(fleet):
            console.print("\n[error]Some instances failed. Check the table above for errors.[/]")
            exit(1)

    def delete_configuration(
        self,
        conf: FleetConfiguration,
        configuration_path: str,
        command_args: argparse.Namespace,
    ):
        if conf.name is None:
            console.print("[error]Configuration specifies no fleet to delete[/]")
            exit(1)

        try:
            self.api.client.fleets.get(
                project_name=self.api.project,
                name=conf.name,
            )
        except ResourceNotExistsError:
            console.print(f"Fleet [code]{conf.name}[/] does not exist")
            exit(1)

        if not command_args.yes and not confirm_ask(f"Delete the fleet [code]{conf.name}[/]?"):
            console.print("\nExiting...")
            return

        with console.status("Deleting fleet..."):
            self.api.client.fleets.delete(project_name=self.api.project, names=[conf.name])
            # Fleet deletion is async. Wait for fleet to be deleted.
            while True:
                try:
                    self.api.client.fleets.get(project_name=self.api.project, name=conf.name)
                except ResourceNotExistsError:
                    break
                else:
                    time.sleep(1)

        console.print(f"Fleet [code]{conf.name}[/] deleted")

    @classmethod
    def register_args(cls, parser: argparse.ArgumentParser):
        configuration_group = parser.add_argument_group(f"{cls.TYPE.value} Options")
        configuration_group.add_argument(
            "-n",
            "--name",
            dest="name",
            help="The fleet name",
        )
        cls.register_env_args(configuration_group)

    def apply_args(self, conf: FleetConfiguration, args: argparse.Namespace, unknown: List[str]):
        if args.name:
            conf.name = args.name
        self.apply_env_vars(conf.env, args)
        if conf.ssh_config is None and conf.env:
            raise ConfigurationError("`env` is currently supported for SSH fleets only")


def _preprocess_spec(spec: FleetSpec):
    ssh_config = spec.configuration.ssh_config
    if ssh_config is not None:
        ssh_config.ssh_key = _resolve_ssh_key(ssh_config.identity_file)
        if ssh_config.proxy_jump is not None:
            ssh_config.proxy_jump.ssh_key = _resolve_ssh_key(ssh_config.proxy_jump.identity_file)
        for host in ssh_config.hosts:
            if not isinstance(host, str):
                host.ssh_key = _resolve_ssh_key(host.identity_file)
                if host.proxy_jump is not None:
                    host.proxy_jump.ssh_key = _resolve_ssh_key(host.proxy_jump.identity_file)


def _resolve_ssh_key(ssh_key_path: Optional[str]) -> Optional[SSHKey]:
    if ssh_key_path is None:
        return None
    ssh_key_path_obj = Path(ssh_key_path).expanduser()
    try:
        private_key = convert_ssh_key_to_pem(ssh_key_path_obj.read_text())
        try:
            pub_key = ssh_key_path_obj.with_suffix(".pub").read_text()
        except FileNotFoundError:
            pub_key = generate_public_key(pkey_from_str(private_key))
        return SSHKey(public=pub_key, private=private_key)
    except OSError as e:
        logger.debug("Got OSError: %s", repr(e))
        console.print(f"[error]Unable to read the SSH key at {ssh_key_path}[/]")
        exit()
    except ValueError as e:
        logger.debug("Key type is not supported", repr(e))
        console.print("[error]Key type is not supported[/]")
        exit()


def _print_plan_header(plan: FleetPlan):
    def th(s: str) -> str:
        return f"[bold]{s}[/bold]"

    spec = plan.get_effective_spec()

    configuration_table = Table(box=None, show_header=False)
    configuration_table.add_column(no_wrap=True)  # key
    configuration_table.add_column()  # value

    configuration_table.add_row(th("Project"), plan.project_name)
    configuration_table.add_row(th("User"), plan.user)
    configuration_table.add_row(th("Configuration"), spec.configuration_path or "?")
    configuration_table.add_row(th("Type"), spec.configuration.type)

    fleet_type = "cloud"
    nodes = spec.configuration.nodes or "-"
    placement = spec.configuration.placement or InstanceGroupPlacement.ANY
    reservation = spec.configuration.reservation
    backends = None
    if spec.configuration.backends is not None:
        backends = ", ".join(b.value for b in spec.configuration.backends)
    regions = None
    if spec.configuration.regions is not None:
        regions = ", ".join(spec.configuration.regions)
    resources = None
    if spec.configuration.resources is not None:
        resources = spec.configuration.resources.pretty_format()
    spot_policy = spec.merged_profile.spot_policy
    if spec.configuration.ssh_config is not None:
        fleet_type = "ssh"
        nodes = len(spec.configuration.ssh_config.hosts)
        resources = None
        spot_policy = None

    configuration_table.add_row(th("Fleet type"), fleet_type)
    configuration_table.add_row(th("Nodes"), str(nodes))
    configuration_table.add_row(th("Placement"), placement.value)
    if backends is not None:
        configuration_table.add_row(th("Backends"), str(backends))
    if regions is not None:
        configuration_table.add_row(th("Regions"), str(regions))
    if resources is not None:
        configuration_table.add_row(th("Resources"), resources)
    if spot_policy is not None:
        configuration_table.add_row(th("Spot policy"), spot_policy)
    if reservation is not None:
        configuration_table.add_row(th("Reservation"), reservation)
    # TODO: [Andrey] Display "Idle duration"

    offers_table = Table(box=None)
    offers_table.add_column("#")
    offers_table.add_column("BACKEND")
    offers_table.add_column("REGION")
    offers_table.add_column("INSTANCE")
    offers_table.add_column("RESOURCES")
    offers_table.add_column("SPOT")
    offers_table.add_column("PRICE")
    offers_table.add_column()

    offers_limit = 3
    print_offers = plan.offers[:offers_limit]

    for index, offer in enumerate(print_offers, start=1):
        resources = offer.instance.resources

        availability = ""
        if offer.availability in {
            InstanceAvailability.NOT_AVAILABLE,
            InstanceAvailability.NO_QUOTA,
        }:
            availability = offer.availability.value.replace("_", " ").title()
        offers_table.add_row(
            f"{index}",
            offer.backend.replace("remote", "ssh"),
            offer.region,
            offer.instance.name,
            resources.pretty_format(),
            "yes" if resources.spot else "no",
            f"${offer.price:3f}".rstrip("0").rstrip("."),
            availability,
            style=None if index == 1 else "secondary",
        )
    if len(plan.offers) > offers_limit:
        offers_table.add_row("", "...", style="secondary")

    console.print(configuration_table)
    console.print()

    if len(print_offers) > 0:
        console.print(offers_table)
        if len(plan.offers) > offers_limit:
            console.print(
                f"[secondary] Shown {len(print_offers)} of {plan.total_offers} offers, "
                f"${plan.max_offer_price:g} max[/]"
            )
        console.print()
    elif fleet_type == "cloud":
        console.print(NO_OFFERS_WARNING)


def _finished_provisioning(fleet: Fleet) -> bool:
    for instance in fleet.instances:
        if instance.status in [
            InstanceStatus.PENDING,
            InstanceStatus.PROVISIONING,
            InstanceStatus.TERMINATING,
        ]:
            return False
    return True


def _failed_provisioning(fleet: Fleet) -> bool:
    for instance in fleet.instances:
        if instance.status == InstanceStatus.TERMINATED:
            return True
    return False


def _apply_plan(api: Client, plan: FleetPlan) -> Fleet:
    try:
        return api.client.fleets.apply_plan(
            project_name=api.project,
            plan=plan,
        )
    except (URLNotFoundError, MethodNotAllowedError):
        # TODO: Remove in 0.20
        return api.client.fleets.create(
            project_name=api.project,
            spec=plan.spec,
        )
