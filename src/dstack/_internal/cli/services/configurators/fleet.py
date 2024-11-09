import argparse
import time
from pathlib import Path
from typing import List, Optional

import requests
from rich.live import Live
from rich.table import Table

from dstack._internal.cli.services.configurators.base import (
    ApplyEnvVarsConfiguratorMixin,
    BaseApplyConfigurator,
)
from dstack._internal.cli.utils.common import (
    LIVE_TABLE_PROVISION_INTERVAL_SECS,
    LIVE_TABLE_REFRESH_RATE_PER_SEC,
    confirm_ask,
    console,
)
from dstack._internal.cli.utils.fleet import get_fleets_table
from dstack._internal.core.errors import ConfigurationError, ResourceNotExistsError
from dstack._internal.core.models.configurations import ApplyConfigurationType
from dstack._internal.core.models.fleets import (
    Fleet,
    FleetConfiguration,
    FleetPlan,
    FleetSpec,
    InstanceGroupPlacement,
)
from dstack._internal.core.models.instances import InstanceAvailability, InstanceStatus, SSHKey
from dstack._internal.utils.logging import get_logger
from dstack._internal.utils.ssh import convert_ssh_key_to_pem, generate_public_key, pkey_from_str
from dstack.api._public import Client
from dstack.api.utils import load_profile

logger = get_logger(__name__)


class FleetConfigurator(ApplyEnvVarsConfiguratorMixin, BaseApplyConfigurator):
    TYPE: ApplyConfigurationType = ApplyConfigurationType.FLEET

    @classmethod
    def register_args(cls, parser: argparse.ArgumentParser):
        cls.register_env_args(parser)

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
            plan = _get_plan(api=self.api, spec=spec)
        _print_plan_header(plan)

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
            if plan.current_resource.spec.configuration == plan.spec.configuration:
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

        with console.status("Creating fleet..."):
            fleet = self.api.client.fleets.create(
                project_name=self.api.project,
                spec=spec,
            )
        if command_args.detach:
            console.print("Fleet configuration submitted. Exiting...")
            return
        console.print()
        try:
            with Live(console=console, refresh_per_second=LIVE_TABLE_REFRESH_RATE_PER_SEC) as live:
                while True:
                    live.update(get_fleets_table([fleet], verbose=True))
                    if _finished_provisioning(fleet):
                        break
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

    def apply_args(self, conf: FleetConfiguration, args: argparse.Namespace, unknown: List[str]):
        self.apply_env_vars(conf.env, args)
        if conf.ssh_config is None and conf.env:
            raise ConfigurationError("`env` is currently supported for SSH fleets only")


def _preprocess_spec(spec: FleetSpec):
    if spec.configuration.ssh_config is not None:
        spec.configuration.ssh_config.ssh_key = _resolve_ssh_key(
            spec.configuration.ssh_config.identity_file
        )
        for host in spec.configuration.ssh_config.hosts:
            if not isinstance(host, str):
                host.ssh_key = _resolve_ssh_key(host.identity_file)


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


def _get_plan(api: Client, spec: FleetSpec) -> FleetPlan:
    try:
        return api.client.fleets.get_plan(
            project_name=api.project,
            spec=spec,
        )
    except requests.exceptions.HTTPError as e:
        # Handle older server versions that do not have /get_plan for fleets
        # TODO: Can be removed in 0.19
        if e.response.status_code == 405:
            logger.warning(
                "Fleet apply plan is not fully supported before 0.18.17. "
                "Update the server to view full-featured apply plan."
            )
            user = api.client.users.get_my_user()
            spec.configuration_path = None
            current_resource = None
            if spec.configuration.name is not None:
                try:
                    current_resource = api.client.fleets.get(
                        project_name=api.project, name=spec.configuration.name
                    )
                except ResourceNotExistsError:
                    pass
            return FleetPlan(
                project_name=api.project,
                user=user.username,
                spec=spec,
                current_resource=current_resource,
                offers=[],
                total_offers=0,
                max_offer_price=0,
            )
        raise e


def _print_plan_header(plan: FleetPlan):
    def th(s: str) -> str:
        return f"[bold]{s}[/bold]"

    configuration_table = Table(box=None, show_header=False)
    configuration_table.add_column(no_wrap=True)  # key
    configuration_table.add_column()  # value

    configuration_table.add_row(th("Project"), plan.project_name)
    configuration_table.add_row(th("User"), plan.user)
    configuration_table.add_row(th("Configuration"), plan.spec.configuration_path or "?")
    configuration_table.add_row(th("Type"), plan.spec.configuration.type)

    fleet_type = "cloud"
    nodes = plan.spec.configuration.nodes or "-"
    placement = plan.spec.configuration.placement or InstanceGroupPlacement.ANY
    reservation = plan.spec.configuration.reservation
    backends = None
    if plan.spec.configuration.backends is not None:
        backends = ", ".join(b.value for b in plan.spec.configuration.backends)
    regions = None
    if plan.spec.configuration.regions is not None:
        regions = ", ".join(plan.spec.configuration.regions)
    resources = None
    if plan.spec.configuration.resources is not None:
        resources = plan.spec.configuration.resources.pretty_format()
    spot_policy = plan.spec.merged_profile.spot_policy
    if plan.spec.configuration.ssh_config is not None:
        fleet_type = "ssh"
        nodes = len(plan.spec.configuration.ssh_config.hosts)
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
            f"${offer.price:g}",
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


def _finished_provisioning(fleet: Fleet) -> bool:
    for instance in fleet.instances:
        if instance.status in [InstanceStatus.PENDING, InstanceStatus.PROVISIONING]:
            return False
    return True
