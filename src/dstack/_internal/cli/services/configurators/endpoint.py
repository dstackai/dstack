import argparse
import shutil
import time
from pathlib import Path

from rich.table import Table

from dstack._internal.cli.services.configurators.base import (
    ApplyEnvVarsConfiguratorMixin,
    BaseApplyConfigurator,
)
from dstack._internal.cli.services.profile import apply_profile_args, register_profile_args
from dstack._internal.cli.utils.common import (
    NO_OFFERS_WARNING,
    confirm_ask,
    console,
    format_backend,
    format_instance_availability,
)
from dstack._internal.cli.utils.endpoint import get_endpoints_table
from dstack._internal.cli.utils.rich import MultiItemStatus
from dstack._internal.core.errors import ConfigurationError, ResourceNotExistsError
from dstack._internal.core.models.configurations import ApplyConfigurationType
from dstack._internal.core.models.endpoints import (
    AnyEndpointProvisioningPlan,
    Endpoint,
    EndpointConfiguration,
    EndpointPlan,
    EndpointPresetPolicy,
    EndpointProvisioningPlanAgent,
    EndpointProvisioningPlanNone,
    EndpointProvisioningPlanPreset,
    EndpointStatus,
)
from dstack._internal.core.models.profiles import Profile, ProfileParams, SpotPolicy
from dstack._internal.utils.common import local_time, make_proxy_url
from dstack.api.utils import load_profile

_NO_ENDPOINT_FLEETS_WARNING = (
    "[error]"
    "The project has no fleets. Create one before submitting an endpoint.\n"
    "See [link]https://dstack.ai/docs/guides/troubleshooting/#no-fleets[/link]"
    "[/]\n"
)


class EndpointConfigurator(
    ApplyEnvVarsConfiguratorMixin,
    BaseApplyConfigurator[EndpointConfiguration],
):
    TYPE = ApplyConfigurationType.ENDPOINT

    def apply_configuration(
        self,
        conf: EndpointConfiguration,
        configuration_path: str,
        command_args: argparse.Namespace,
        configurator_args: argparse.Namespace,
    ):
        self.apply_args(conf, configurator_args)
        with console.status("Getting apply plan..."):
            plan = self.api.client.endpoints.get_plan(
                project_name=self.api.project,
                configuration=conf,
                configuration_path=configuration_path,
            )
        no_fleets = False
        if _preset_plan_has_no_offers(plan.provisioning_plan):
            if len(self.api.client.fleets.list(self.api.project, include_imported=True)) == 0:
                no_fleets = True
        _print_endpoint_plan(plan, no_fleets=no_fleets)

        confirm_message = _get_apply_confirm_message(plan)
        current_resource = _get_non_terminal_current_resource(plan)
        stop_run_name = None
        if current_resource is not None:
            if current_resource.configuration == plan.configuration:
                console.print(
                    f"Endpoint [code]{current_resource.name}[/] already exists."
                    " Detected no changes."
                )
                if command_args.yes and not command_args.force:
                    console.print("Use --force to apply anyway.")
                    return
            else:
                # TODO: Replace v1 stop/recreate with endpoint in-place update
                # via service rolling deployment once endpoint versioning exists.
                console.print(
                    f"Endpoint [code]{current_resource.name}[/] already exists."
                    " Detected changes that [error]cannot[/] be updated in-place."
                )
        else:
            serving_run_name = _get_endpoint_serving_run_name(plan)
            same_name_run = None
            if serving_run_name is not None:
                same_name_run = self.api.runs.get(serving_run_name)
            if same_name_run is not None and not same_name_run.status.is_finished():
                stop_run_name = same_name_run.name
                console.print(
                    f"Active run [code]{stop_run_name}[/] already exists."
                    " The endpoint will use this backing service run name."
                )
                confirm_message = _get_apply_confirm_message(
                    plan,
                    stop_run_name=stop_run_name,
                )

        if not command_args.yes and not confirm_ask(confirm_message):
            console.print("\nExiting...")
            return

        if current_resource is not None:
            with console.status("Stopping existing endpoint..."):
                self.api.client.endpoints.stop(
                    project_name=self.api.project,
                    names=[current_resource.name],
                )
                while True:
                    try:
                        endpoint = self.api.client.endpoints.get(
                            project_name=self.api.project,
                            name=current_resource.name,
                        )
                    except ResourceNotExistsError:
                        break
                    if endpoint.status.is_finished():
                        break
                    time.sleep(1)

        if stop_run_name is not None:
            with console.status("Stopping run..."):
                self.api.client.runs.stop(self.api.project, [stop_run_name], abort=False)
                while True:
                    run = self.api.runs.get(stop_run_name)
                    if run is None or run.status.is_finished():
                        break
                    time.sleep(1)

        with console.status("Creating endpoint..."):
            endpoint = self.api.client.endpoints.create(
                project_name=self.api.project,
                configuration=conf,
            )
        if command_args.detach:
            _print_submitted_endpoint_message(endpoint)
            return
        self._follow_endpoint_apply(endpoint)

    def delete_configuration(
        self,
        conf: EndpointConfiguration,
        configuration_path: str,
        command_args: argparse.Namespace,
    ):
        raise ConfigurationError(
            "`dstack delete` does not support endpoint configurations. "
            "Use `dstack endpoint stop <name>`."
        )

    @classmethod
    def register_args(cls, parser: argparse.ArgumentParser):
        configuration_group = parser.add_argument_group(f"{cls.TYPE.value} Options")
        configuration_group.add_argument(
            "-n",
            "--name",
            dest="name",
            help="The endpoint name",
        )
        cls.register_env_args(configuration_group)
        register_profile_args(parser)

    def apply_args(self, conf: EndpointConfiguration, args: argparse.Namespace):
        profile = load_profile(Path.cwd(), args.profile)
        _apply_profile(conf, profile)
        apply_profile_args(args, conf)
        if args.name:
            conf.name = args.name
        self.apply_env_vars(conf.env, args)

    def _follow_endpoint_apply(self, endpoint: Endpoint):
        try:
            with MultiItemStatus(_get_apply_status(endpoint), console=console) as live:
                while not _is_endpoint_apply_finished(endpoint):
                    live.update(
                        get_endpoints_table([endpoint], format_date=local_time),
                        status=_get_apply_status(endpoint),
                    )
                    time.sleep(2)
                    endpoint = self.api.client.endpoints.get(
                        project_name=self.api.project,
                        name=endpoint.name,
                    )
        except KeyboardInterrupt:
            console.print("\nDetached")
            return

        _make_endpoint_url_absolute(endpoint, self.api.client.base_url)
        console.print(
            get_endpoints_table(
                [endpoint],
                verbose=endpoint.status == EndpointStatus.RUNNING,
                format_date=local_time,
            )
        )
        console.print(
            f"\nEndpoint [code]{endpoint.name}[/] provisioning completed "
            f"[secondary]({endpoint.status.value})[/]"
        )
        _print_finished_endpoint_message(endpoint)
        if endpoint.status == EndpointStatus.FAILED:
            exit(1)


def _apply_profile(conf: EndpointConfiguration, profile: Profile):
    for field in ProfileParams.__fields__:
        value = getattr(profile, field)
        if value is not None:
            setattr(conf, field, value)


def _is_endpoint_apply_finished(endpoint: Endpoint) -> bool:
    return endpoint.status in (
        EndpointStatus.RUNNING,
        EndpointStatus.STOPPED,
        EndpointStatus.FAILED,
    )


def _get_apply_status(endpoint: Endpoint) -> str:
    return f"Provisioning endpoint [code]{endpoint.name}[/]..."


def _print_finished_endpoint_message(endpoint: Endpoint) -> None:
    if endpoint.status == EndpointStatus.RUNNING:
        if endpoint.url is not None:
            console.print(f"[code]{endpoint.url}[/code]")
        return

    message = endpoint.status_message or endpoint.error
    if message is None:
        message = endpoint.status.value.capitalize()
    console.print(f"[error]{message}[/error]")


def _print_endpoint_plan(plan: EndpointPlan, no_fleets: bool = False):
    def th(s: str) -> str:
        return f"[bold]{s}[/bold]"

    props = Table(box=None, show_header=False)
    props.add_column(no_wrap=True)
    props.add_column()
    props.add_row(th("Project"), plan.project_name)
    props.add_row(th("User"), plan.user)
    if plan.configuration_path is not None:
        props.add_row(th("Configuration"), plan.configuration_path)
    props.add_row(th("Type"), plan.configuration.type)
    props.add_row(th("Spot policy"), _format_spot_policy(plan))
    props.add_row(th("Max price"), _format_max_price(plan))
    props.add_row(th("Preset policy"), plan.preset_policy.value)
    if isinstance(plan.provisioning_plan, EndpointProvisioningPlanPreset):
        props.add_row(th("Preset"), plan.provisioning_plan.preset_name)
    elif (
        isinstance(plan.provisioning_plan, EndpointProvisioningPlanAgent)
        and plan.provisioning_plan.max_budget is not None
    ):
        props.add_row(th("Agent budget"), _format_price_limit(plan.provisioning_plan.max_budget))
    console.print(props)
    console.print()

    if isinstance(plan.provisioning_plan, EndpointProvisioningPlanPreset):
        _print_preset_plan_offers(plan.provisioning_plan, no_fleets=no_fleets)
    elif isinstance(plan.provisioning_plan, EndpointProvisioningPlanNone):
        style = "error" if plan.preset_policy == EndpointPresetPolicy.CREATE else "warning"
        console.print(f"[{style}]{plan.provisioning_plan.reason}[/]")
        console.print()
    elif isinstance(plan.provisioning_plan, EndpointProvisioningPlanAgent):
        # TODO: Consider showing initial candidate offers for agent provisioning as
        # non-binding context. Do not present them as selected resources/final hardware.
        if plan.provisioning_plan.reason is not None:
            console.print(f"[warning]{plan.provisioning_plan.reason}[/]")
            console.print()


def _get_apply_confirm_message(
    plan: EndpointPlan,
    stop_run_name: str | None = None,
) -> str:
    current_resource = _get_non_terminal_current_resource(plan)
    if current_resource is not None:
        return f"Stop and override the endpoint [code]{current_resource.name}[/]?"
    if stop_run_name is not None:
        return f"Stop and override the run [code]{stop_run_name}[/]?"
    return "Create the endpoint?"


def _get_endpoint_serving_run_name(plan: EndpointPlan) -> str | None:
    if _get_non_terminal_current_resource(plan) is not None:
        return None
    if isinstance(plan.provisioning_plan, EndpointProvisioningPlanPreset):
        return plan.provisioning_plan.service_name
    return None


def _get_non_terminal_current_resource(plan: EndpointPlan) -> Endpoint | None:
    if plan.current_resource is None or plan.current_resource.status.is_finished():
        return None
    return plan.current_resource


def _format_spot_policy(plan: EndpointPlan) -> str:
    if isinstance(plan.provisioning_plan, EndpointProvisioningPlanPreset):
        values = {job_offers.spot for job_offers in plan.provisioning_plan.job_offers}
        if len(values) == 1:
            return _format_spot(next(iter(values)))
        return "mixed"
    return _format_endpoint_spot_policy(plan.configuration.spot_policy)


def _format_endpoint_spot_policy(spot_policy: SpotPolicy | None) -> str:
    if spot_policy == SpotPolicy.SPOT:
        return "spot"
    if spot_policy == SpotPolicy.ONDEMAND:
        return "on-demand"
    return "auto"


def _format_spot(spot: bool | None) -> str:
    if spot is None:
        return "auto"
    return "spot" if spot else "on-demand"


def _format_max_price(plan: EndpointPlan) -> str:
    if isinstance(plan.provisioning_plan, EndpointProvisioningPlanPreset):
        values = {job_offers.max_price for job_offers in plan.provisioning_plan.job_offers}
        if len(values) == 1:
            return _format_price_limit(next(iter(values)))
        return "mixed"
    return _format_price_limit(plan.configuration.max_price)


def _format_price_limit(max_price: float | None) -> str:
    return f"${max_price:3f}".rstrip("0").rstrip(".") if max_price else "off"


def _preset_plan_has_no_offers(
    provisioning_plan: AnyEndpointProvisioningPlan,
) -> bool:
    if not isinstance(provisioning_plan, EndpointProvisioningPlanPreset):
        return False
    return not any(job_offers.offers for job_offers in provisioning_plan.job_offers)


def _print_preset_plan_offers(
    provisioning_plan: EndpointProvisioningPlanPreset,
    no_fleets: bool = False,
) -> None:
    if _preset_plan_has_no_offers(provisioning_plan):
        console.print(_NO_ENDPOINT_FLEETS_WARNING if no_fleets else NO_OFFERS_WARNING)
        return

    show_replica_groups = len(provisioning_plan.job_offers) > 1 or any(
        job_offers.replica_group != "0" for job_offers in provisioning_plan.job_offers
    )
    offers = Table(box=None, expand=shutil.get_terminal_size(fallback=(120, 40)).columns <= 110)
    offers.add_column("#")
    if show_replica_groups:
        offers.add_column("GROUP", no_wrap=True)
    offers.add_column("BACKEND", style="grey58")
    offers.add_column("RESOURCES")
    offers.add_column("INSTANCE TYPE", style="grey58", no_wrap=True)
    offers.add_column("PRICE", style="grey58")
    offers.add_column()
    offer_num = 0
    total_offers = 0
    for job_offers in provisioning_plan.job_offers:
        total_offers += job_offers.total_offers
        for offer in job_offers.offers:
            offer_num += 1
            row = [
                str(offer_num),
                format_backend(offer.backend, offer.region),
                offer.instance.resources.pretty_format(include_spot=True),
                offer.instance.name,
                f"${offer.price:.4f}".rstrip("0").rstrip("."),
                format_instance_availability(offer.availability),
            ]
            if show_replica_groups:
                row.insert(1, job_offers.replica_group)
            offers.add_row(*row, style=None if offer_num == 1 else "secondary")
        if job_offers.total_offers > len(job_offers.offers):
            row = ["", "..."]
            if show_replica_groups:
                row.insert(1, job_offers.replica_group)
            offers.add_row(*row, style="secondary")
    console.print(offers)
    if total_offers > offer_num:
        console.print(f"[secondary] Shown {offer_num} of {total_offers} offers[/]")
    console.print()


def _print_submitted_endpoint_message(endpoint: Endpoint) -> None:
    console.print(f"Endpoint [code]{endpoint.name}[/] submitted, detaching...")


def _make_endpoint_url_absolute(endpoint: Endpoint, server_url: str) -> None:
    if endpoint.url is None:
        return
    endpoint.url = make_proxy_url(server_url=server_url, proxy_url=endpoint.url)
