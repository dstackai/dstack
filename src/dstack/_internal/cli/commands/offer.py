import argparse
import contextlib
import json
from pathlib import Path

from rich.table import Table

from dstack._internal.cli.commands import APIBaseCommand
from dstack._internal.cli.services.configurators.run import (
    BaseRunConfigurator,
)
from dstack._internal.cli.utils.common import console
from dstack._internal.core.models.configurations import (
    ApplyConfigurationType,
    TaskConfiguration,
)
from dstack._internal.core.models.instances import InstanceAvailability
from dstack._internal.core.models.runs import RunSpec
from dstack.api.utils import load_profile


class OfferConfigurator(BaseRunConfigurator):
    # TODO: The command currently uses `BaseRunConfigurator` to register arguments.
    #   This includes --env, --retry-policy, and other arguments that are unnecessary for this command.
    #   Eventually, we should introduce a base `OfferConfigurator` that doesn't include those arguments—
    #   `BaseRunConfigurator` will inherit from `OfferConfigurator`.
    #
    #   Additionally, it should have its own type: `ApplyConfigurationType.OFFER`.
    TYPE = ApplyConfigurationType.TASK

    @classmethod
    def register_args(
        cls,
        parser: argparse.ArgumentParser,
    ):
        super().register_args(parser, default_max_offers=50)


# TODO: Support aggregated offers
# TODO: Add tests
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
        OfferConfigurator.register_args(self._parser)

    def _command(self, args: argparse.Namespace):
        super()._command(args)
        conf = TaskConfiguration(commands=[":"])

        configurator = OfferConfigurator(api_client=self.api)
        configurator.apply_args(conf, args, [])
        profile = load_profile(Path.cwd(), profile_name=args.profile)

        run_spec = RunSpec(
            configuration=conf,
            ssh_key_pub="(dummy)",
            profile=profile,
        )
        if args.format == "plain":
            status = console.status("Getting offers...")
        else:
            status = contextlib.nullcontext()
        with status:
            run_plan = self.api.client.runs.get_plan(
                self.api.project,
                run_spec,
                max_offers=args.max_offers,
            )

        job_plan = run_plan.job_plans[0]

        if args.format == "json":
            output = {
                "project": run_plan.project_name,
                "user": run_plan.user,
                "resources": job_plan.job_spec.requirements.resources.dict(),
                "max_price": (job_plan.job_spec.requirements.max_price),
                "spot": run_spec.configuration.spot_policy,
                "reservation": run_plan.run_spec.configuration.reservation,
                "offers": [],
                "total_offers": job_plan.total_offers,
            }

            for offer in job_plan.offers:
                output["offers"].append(
                    {
                        "backend": (
                            "ssh" if offer.backend.value == "remote" else offer.backend.value
                        ),
                        "region": offer.region,
                        "resources": offer.instance.resources.dict(),
                        "spot": offer.instance.resources.spot,
                        "price": float(offer.price),
                        "availability": offer.availability.value,
                    }
                )

            print(json.dumps(output, indent=2))
            return

        props = Table(box=None, show_header=False)
        props.add_column(no_wrap=True)  # key
        props.add_column()  # value

        req = job_plan.job_spec.requirements
        pretty_req = req.pretty_format(resources_only=True)
        max_price = f"${req.max_price:g}" if req.max_price else "-"
        profile = run_plan.run_spec.merged_profile
        if req.spot is None:
            spot_policy = "auto"
        elif req.spot:
            spot_policy = "spot"
        else:
            spot_policy = "on-demand"

        def th(s: str) -> str:
            return f"[bold]{s}[/bold]"

        props.add_row(th("Project"), run_plan.project_name)
        props.add_row(th("User"), run_plan.user)
        props.add_row(th("Resources"), pretty_req)
        props.add_row(th("Max price"), max_price)
        props.add_row(th("Spot policy"), spot_policy)
        props.add_row(th("Reservation"), run_plan.run_spec.configuration.reservation or "-")
        console.print(props)
        console.print()

        table = Table(box=None)
        table.add_column("#")
        table.add_column("BACKEND")
        table.add_column("REGION")
        table.add_column("RESOURCES")
        table.add_column("SPOT")
        table.add_column("PRICE", justify="right")
        table.add_column("")

        offers = run_plan.job_plans[0].offers
        for i, offer in enumerate(offers, 1):
            price = f"${offer.price:.3f}"
            availability = ""
            if offer.availability in {
                InstanceAvailability.NOT_AVAILABLE,
                InstanceAvailability.NO_QUOTA,
                InstanceAvailability.IDLE,
                InstanceAvailability.BUSY,
            }:
                availability = offer.availability.value.replace("_", " ").lower()

            # TODO: rename `remote` to `ssh` everywhere
            table.add_row(
                str(i),
                "ssh" if offer.backend.value == "remote" else offer.backend.value,
                offer.region,
                offer.instance.resources.pretty_format(),
                "yes" if offer.instance.resources.spot else "no",
                price,
                availability,
            )

        if job_plan.total_offers > len(job_plan.offers):
            table.add_row("", "...", style="secondary")
        console.print(table)
        if job_plan.total_offers > len(job_plan.offers):
            console.print(
                f"[secondary]Shown {len(job_plan.offers)} of {job_plan.total_offers} offers, "
                f"${job_plan.max_price:g} max[/]"
            )
        console.print()
