import argparse
from contextlib import nullcontext
from pathlib import Path
from typing import List, Literal, Optional, cast

from rich.table import Table

from dstack._internal.cli.commands import APIBaseCommand
from dstack._internal.cli.models.offers import OfferCommandOutput, OfferRequirements
from dstack._internal.cli.services.profile import (
    apply_profile_args,
    load_profile_from_args,
    register_profile_args,
)
from dstack._internal.cli.services.resources import apply_resources_args, register_resources_args
from dstack._internal.cli.utils.common import NO_OFFERS_WARNING, console
from dstack._internal.cli.utils.gpu import print_gpu_json, print_gpu_table
from dstack._internal.cli.utils.offers import print_offers_table
from dstack._internal.core.errors import CLIError
from dstack._internal.core.models.configurations import TaskConfiguration
from dstack._internal.core.models.instances import InstanceOfferWithAvailability
from dstack._internal.core.models.profiles import SpotPolicy
from dstack._internal.core.models.resources import ResourcesSpec
from dstack._internal.core.models.runs import Requirements, RunPlan, RunSpec, get_policy_map


class OfferCommand(APIBaseCommand):
    NAME = "offer"
    DESCRIPTION = "List offers"

    def _register(self):
        super()._register()
        self._parser.add_argument(
            "--format",
            choices=["plain", "json"],
            default="plain",
            help="Output format (default: plain)",
        )
        self._parser.add_argument(
            "--json",
            action="store_const",
            const="json",
            dest="format",
            help="Output in JSON format (equivalent to --format json)",
        )
        self._parser.add_argument(
            "--group-by",
            action="append",
            help=(
                "Group results by fields ([code]gpu[/code], [code]backend[/code], [code]region[/code], [code]count[/code]). "
                "Optional, but if used, must include [code]gpu[/code]. "
                "The use of [code]region[/code] also requires [code]backend[/code]. "
                "Can be repeated or comma-separated (e.g. [code]--group-by gpu,backend[/code])."
            ),
        )
        self._parser.add_argument(
            "--max-offers",
            help="Number of offers to show",
            type=int,
            default=50,
        )
        self._parser.add_argument(
            "--full-offers",
            action="store_true",
            help="Show full offers not adjusted by requirements",
        )
        self._parser.add_argument(
            "--unallocated",
            action="store_true",
            help="Subtract allocated resources to show only unallocated resources",
        )
        resources_group = self._parser.add_argument_group("Resources")
        register_resources_args(resources_group)
        # TODO: register only relevant options
        register_profile_args(self._parser)

    def _command(self, args: argparse.Namespace):
        super()._command(args)
        group_by = _process_group_by_args(args.group_by or [])
        with console.status("Getting offers...") if args.format == "plain" else nullcontext():
            if group_by:
                self._list_gpus(args, group_by)
            else:
                self._list_offers(args)

    def _list_offers(self, args: argparse.Namespace) -> None:
        run_spec = _get_run_spec(args)
        run_plan = self.api.client.runs.get_plan(
            project_name=self.api.project,
            run_spec=run_spec,
            max_offers=args.max_offers,
            full_offers=args.full_offers,
            unallocated_resources=args.unallocated,
        )
        job_plan = run_plan.job_plans[0]
        if args.format == "plain":
            _print_offers_header(
                project_name=self.api.project,
                requirements=job_plan.job_spec.requirements,
            )
            _print_offers_table(
                offers=job_plan.offers,
                total_offers=job_plan.total_offers,
                max_price=job_plan.max_price,
                show_fleet_hint=run_spec.merged_profile.fleets is None,
            )
        elif args.format == "json":
            _print_offers_json(run_plan)
        else:
            raise NotImplementedError(args.format)

    def _list_gpus(self, args: argparse.Namespace, group_by: list[str]) -> None:
        run_spec = _get_run_spec(args)
        gpus = self.api.client.gpus.list_gpus(
            project_name=self.api.project,
            run_spec=run_spec,
            group_by=[g for g in group_by if g != "gpu"],
            full_offers=args.full_offers,
            unallocated_resources=args.unallocated,
        )
        if args.format == "plain":
            print_gpu_table(gpus, run_spec, group_by, self.api.project)
        elif args.format == "json":
            print_gpu_json(
                gpus,
                run_spec,
                cast(List[Literal["gpu", "backend", "region", "count"]], group_by),
                self.api.project,
            )
        else:
            raise NotImplementedError(args.format)


def _process_group_by_args(group_by_args: List[str]) -> List[str]:
    valid_choices = {"gpu", "backend", "region", "count"}
    processed = []

    for arg in group_by_args:
        values = [v.strip() for v in arg.split(",") if v.strip()]
        for value in values:
            if value in valid_choices:
                processed.append(value)
            else:
                raise CLIError(
                    f"Invalid group-by value: '{value}'. Valid choices are: {', '.join(sorted(valid_choices))}"
                )

    if processed and "gpu" not in processed:
        group_values = ", ".join(processed)
        raise CLIError(f"Cannot group by '{group_values}' without also grouping by 'gpu'")

    return processed


def _get_run_spec(args: argparse.Namespace) -> RunSpec:
    # Set image and user so that the server (a) does not default gpu.vendor
    # to nvidia — `dstack offer` should show all vendors, and (b) does not
    # attempt to pull image config from the Docker registry.
    conf = TaskConfiguration(
        resources=ResourcesSpec.unconstrained(),
        commands=[":"],
        image="scratch",
        user="root",
    )
    apply_resources_args(args, conf)
    apply_profile_args(args, conf)
    profile = load_profile_from_args(args=args, repo_dir=Path.cwd())
    return RunSpec(
        configuration=conf,
        profile=profile,
    )


def _print_offers_header(
    project_name: str,
    requirements: Requirements,
):
    def th(s: str) -> str:
        return f"[bold]{s}[/bold]"

    props = Table(box=None, show_header=False)
    props.add_column(no_wrap=True)  # key
    props.add_column()  # value

    pretty_req = requirements.pretty_format(resources_only=True)
    max_price = (
        f"${requirements.max_price:3f}".rstrip("0").rstrip(".")
        if requirements.max_price
        else "off"
    )

    if requirements.spot is None:
        spot_policy = "auto"
    elif requirements.spot:
        spot_policy = "spot"
    else:
        spot_policy = "on-demand"

    props.add_row(th("Project"), project_name)
    props.add_row(th("Resources"), pretty_req)
    props.add_row(th("Spot policy"), spot_policy)
    props.add_row(th("Max price"), max_price)
    console.print(props)
    console.print()


_FLEET_HINT = (
    "Hint: Existing fleets are ignored, and all available offers are shown."
    " To filter by fleet, pass --fleet NAME."
)


def _print_offers_table(
    offers: list[InstanceOfferWithAvailability],
    total_offers: int,
    max_price: Optional[float],
    show_fleet_hint: bool,
):
    if len(offers) > 0:
        show_fleet_hint_before_table = (
            show_fleet_hint and total_offers <= len(offers) and len(offers) < 3
        )
        show_fleet_hint_after_table = show_fleet_hint and not show_fleet_hint_before_table
        if show_fleet_hint_before_table:
            console.print(f"[secondary]{_FLEET_HINT}[/]")
            console.print()
        print_offers_table(
            offers=offers,
            total_offers=total_offers,
            max_price=max_price or 0.0,
            mute_tail_rows=False,
        )
        console.print()
        if show_fleet_hint_after_table:
            console.print(f"[secondary]{_FLEET_HINT}[/]")
    else:
        console.print(NO_OFFERS_WARNING)


def _print_offers_json(run_plan: RunPlan):
    job_plan = run_plan.job_plans[0]
    requirements = OfferRequirements(
        resources=job_plan.job_spec.requirements.resources,
        max_price=job_plan.job_spec.requirements.max_price,
        spot=get_policy_map(run_plan.run_spec.configuration.spot_policy, default=SpotPolicy.AUTO),
        reservation=run_plan.run_spec.configuration.reservation,
    )
    output = OfferCommandOutput(
        project=run_plan.project_name,
        user=run_plan.user,
        requirements=requirements,
        offers=job_plan.offers,
        total_offers=job_plan.total_offers,
    )
    print(output.json())
