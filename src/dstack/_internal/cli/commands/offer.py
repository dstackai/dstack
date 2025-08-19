import argparse
from pathlib import Path
from typing import List

from dstack._internal.cli.commands import APIBaseCommand
from dstack._internal.cli.services.configurators.run import BaseRunConfigurator
from dstack._internal.cli.utils.common import console
from dstack._internal.cli.utils.gpu import print_gpu_json, print_gpu_table
from dstack._internal.cli.utils.run import print_offers_json, print_run_plan
from dstack._internal.core.errors import CLIError
from dstack._internal.core.models.configurations import ApplyConfigurationType, TaskConfiguration
from dstack._internal.core.models.runs import RunSpec
from dstack._internal.server.schemas.gpus import GpuGroup
from dstack.api.utils import load_profile


class OfferConfigurator(BaseRunConfigurator):
    TYPE = ApplyConfigurationType.TASK

    @classmethod
    def register_args(
        cls,
        parser: argparse.ArgumentParser,
    ):
        super().register_args(parser, default_max_offers=50)
        parser.add_argument(
            "--group-by",
            action="append",
            help=(
                "Group results by fields ([code]gpu[/code], [code]backend[/code], [code]region[/code], [code]count[/code]). "
                "Optional, but if used, must include [code]gpu[/code]. "
                "The use of [code]region[/code] also requires [code]backend[/code]. "
                "Can be repeated or comma-separated (e.g. [code]--group-by gpu,backend[/code])."
            ),
        )


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

        if args.group_by:
            args.group_by = self._process_group_by_args(args.group_by)

        if args.group_by and "gpu" not in args.group_by:
            group_values = ", ".join(args.group_by)
            raise CLIError(f"Cannot group by '{group_values}' without also grouping by 'gpu'")

        if args.format == "plain":
            with console.status("Getting offers..."):
                if args.group_by:
                    gpus = self._list_gpus(args, run_spec)
                    print_gpu_table(gpus, run_spec, args.group_by, self.api.project)
                else:
                    run_plan = self.api.client.runs.get_plan(
                        self.api.project,
                        run_spec,
                        max_offers=args.max_offers,
                    )
                    print_run_plan(run_plan, include_run_properties=False)
        else:
            if args.group_by:
                gpus = self._list_gpus(args, run_spec)
                print_gpu_json(gpus, run_spec, args.group_by, self.api.project)
            else:
                run_plan = self.api.client.runs.get_plan(
                    self.api.project,
                    run_spec,
                    max_offers=args.max_offers,
                )
                print_offers_json(run_plan, run_spec)

    def _process_group_by_args(self, group_by_args: List[str]) -> List[str]:
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

        return processed

    def _list_gpus(self, args: List[str], run_spec: RunSpec) -> List[GpuGroup]:
        group_by = [g for g in args.group_by if g != "gpu"] or None
        return self.api.client.gpus.list_gpus(
            self.api.project,
            run_spec,
            group_by=group_by,
        )
