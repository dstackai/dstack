import argparse
import contextlib
import json
from pathlib import Path

from dstack._internal.cli.commands import APIBaseCommand
from dstack._internal.cli.services.configurators.run import (
    BaseRunConfigurator,
)
from dstack._internal.cli.utils.common import console
from dstack._internal.cli.utils.run import print_run_plan
from dstack._internal.core.models.configurations import (
    ApplyConfigurationType,
    TaskConfiguration,
)
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
                        "instance_type": offer.instance.name,
                        "resources": offer.instance.resources.dict(),
                        "spot": offer.instance.resources.spot,
                        "price": float(offer.price),
                        "availability": offer.availability.value,
                    }
                )

            print(json.dumps(output, indent=2))
            return
        else:
            print_run_plan(run_plan, include_run_properties=False)
