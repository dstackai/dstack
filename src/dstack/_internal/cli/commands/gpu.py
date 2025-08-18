import argparse
import contextlib
import json
import shutil
from pathlib import Path

from rich.table import Table

from dstack._internal.cli.commands import APIBaseCommand
from dstack._internal.cli.services.configurators.run import BaseRunConfigurator
from dstack._internal.cli.utils.common import console
from dstack._internal.core.models.configurations import (
    ApplyConfigurationType,
    TaskConfiguration,
)
from dstack._internal.core.models.profiles import SpotPolicy
from dstack._internal.core.models.runs import Requirements, RunSpec, get_policy_map
from dstack.api.utils import load_profile


class GpuConfigurator(BaseRunConfigurator):
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
            choices=["backend", "region", "count"],
            help="Group GPUs by backend, region, and/or count. Can be specified multiple times.",
        )


class GpuCommand(APIBaseCommand):
    NAME = "gpu"
    DESCRIPTION = "List available GPUs"

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
        GpuConfigurator.register_args(self._parser)

    def _command(self, args: argparse.Namespace):
        super()._command(args)
        conf = TaskConfiguration(commands=[":"])

        configurator = GpuConfigurator(api_client=self.api)
        configurator.apply_args(conf, args, [])
        profile = load_profile(Path.cwd(), profile_name=args.profile)

        run_spec = RunSpec(
            configuration=conf,
            ssh_key_pub="(dummy)",
            profile=profile,
        )

        if args.format == "plain":
            status = console.status("Getting GPU information...")
        else:
            status = contextlib.nullcontext()

        with status:
            gpu_response = self.api.client.gpus.list_gpus(
                self.api.project,
                run_spec,
                group_by=args.group_by,
            )

        if args.format == "json":
            req = Requirements(
                resources=run_spec.configuration.resources,
                max_price=run_spec.merged_profile.max_price,
                spot=get_policy_map(run_spec.merged_profile.spot_policy, default=SpotPolicy.AUTO),
                reservation=run_spec.merged_profile.reservation,
            )

            if req.spot is None:
                spot_policy = "auto"
            elif req.spot:
                spot_policy = "spot"
            else:
                spot_policy = "on-demand"

            output = {
                "project": self.api.project,
                "user": "admin",  # TODO: Get actual user name
                "resources": req.resources.dict(),
                "spot_policy": spot_policy,
                "max_price": req.max_price,
                "reservation": run_spec.configuration.reservation,
                "group_by": args.group_by,
                "gpus": [],
            }

            for gpu_group in gpu_response.gpus:
                gpu_data = {
                    "name": gpu_group.name,
                    "memory_mib": gpu_group.memory_mib,
                    "vendor": gpu_group.vendor.value,
                    "availability": [av.value for av in gpu_group.availability],
                    "spot": gpu_group.spot,
                    "count": {"min": gpu_group.count.min, "max": gpu_group.count.max},
                    "price": {"min": gpu_group.price.min, "max": gpu_group.price.max},
                }

                if gpu_group.backend:
                    gpu_data["backend"] = gpu_group.backend.value
                if gpu_group.backends:
                    gpu_data["backends"] = [b.value for b in gpu_group.backends]
                if gpu_group.region:
                    gpu_data["region"] = gpu_group.region
                if gpu_group.regions:
                    gpu_data["regions"] = gpu_group.regions

                output["gpus"].append(gpu_data)

            print(json.dumps(output, indent=2))
            return
        else:
            self._print_gpu_table(gpu_response, run_spec, args.group_by)

    def _print_gpu_table(self, gpu_response, run_spec, group_by):
        self._print_filter_info(run_spec, group_by)

        has_single_backend = any(gpu_group.backend for gpu_group in gpu_response.gpus)
        has_single_region = any(gpu_group.region for gpu_group in gpu_response.gpus)
        has_multiple_regions = any(gpu_group.regions for gpu_group in gpu_response.gpus)

        if has_single_backend and has_single_region:
            backend_column = "BACKEND"
            region_column = "REGION"
        elif has_single_backend and has_multiple_regions:
            backend_column = "BACKEND"
            region_column = "REGIONS"
        else:
            backend_column = "BACKENDS"
            region_column = None

        table = Table(box=None, expand=shutil.get_terminal_size(fallback=(120, 40)).columns <= 110)
        table.add_column("#")
        table.add_column("GPU", no_wrap=True, ratio=2)
        table.add_column("SPOT", style="grey58", ratio=1)
        table.add_column("$/GPU", style="grey58", ratio=1)
        table.add_column(backend_column, style="grey58", ratio=2)
        if region_column:
            table.add_column(region_column, style="grey58", ratio=2)
        table.add_column()

        for i, gpu_group in enumerate(gpu_response.gpus, start=1):
            backend_text = ""
            if gpu_group.backend:
                backend_text = gpu_group.backend.value
            elif gpu_group.backends:
                backend_text = ", ".join(b.value for b in gpu_group.backends)

            region_text = ""
            if gpu_group.region:
                region_text = gpu_group.region
            elif gpu_group.regions:
                if len(gpu_group.regions) <= 3:
                    region_text = ", ".join(gpu_group.regions)
                else:
                    region_text = f"{len(gpu_group.regions)} regions"

            if not region_column:
                if gpu_group.regions and len(gpu_group.regions) > 3:
                    shortened_region_text = f"{len(gpu_group.regions)} regions"
                    backends_display = (
                        f"{backend_text} ({shortened_region_text})"
                        if shortened_region_text
                        else backend_text
                    )
                else:
                    backends_display = (
                        f"{backend_text} ({region_text})" if region_text else backend_text
                    )
            else:
                backends_display = backend_text

            memory_gb = f"{gpu_group.memory_mib // 1024}GB"
            if gpu_group.count.min == gpu_group.count.max:
                count_range = str(gpu_group.count.min)
            else:
                count_range = f"{gpu_group.count.min}..{gpu_group.count.max}"

            # Always include count in GPU spec format: <gpu name>:<memory>:<count>
            gpu_spec = f"{gpu_group.name}:{memory_gb}:{count_range}"

            spot_types = []
            if "spot" in gpu_group.spot:
                spot_types.append("spot")
            if "on-demand" in gpu_group.spot:
                spot_types.append("on-demand")
            spot_display = ", ".join(spot_types)

            if gpu_group.price.min == gpu_group.price.max:
                price_display = f"{gpu_group.price.min:.4f}".rstrip("0").rstrip(".")
            else:
                min_formatted = f"{gpu_group.price.min:.4f}".rstrip("0").rstrip(".")
                max_formatted = f"{gpu_group.price.max:.4f}".rstrip("0").rstrip(".")
                price_display = f"{min_formatted}..{max_formatted}"

            availability = ""
            has_available = any(av.is_available() for av in gpu_group.availability)
            has_unavailable = any(not av.is_available() for av in gpu_group.availability)

            if has_unavailable and not has_available:
                for av in gpu_group.availability:
                    if av.value in {"not_available", "no_quota", "idle", "busy"}:
                        availability = av.value.replace("_", " ").lower()
                        break

            secondary_style = "grey58"
            row_data = [
                f"[{secondary_style}]{i}[/]",
                gpu_spec,
                f"[{secondary_style}]{spot_display}[/]",
                f"[{secondary_style}]{price_display}[/]",
                f"[{secondary_style}]{backends_display}[/]",
            ]
            if region_column:
                row_data.append(f"[{secondary_style}]{region_text}[/]")
            row_data.append(f"[{secondary_style}]{availability}[/]")

            table.add_row(*row_data)

        console.print(table)

    def _print_filter_info(self, run_spec, group_by):
        props = Table(box=None, show_header=False)
        props.add_column(no_wrap=True)
        props.add_column()

        req = Requirements(
            resources=run_spec.configuration.resources,
            max_price=run_spec.merged_profile.max_price,
            spot=get_policy_map(run_spec.merged_profile.spot_policy, default=SpotPolicy.AUTO),
            reservation=run_spec.merged_profile.reservation,
        )

        pretty_req = req.pretty_format(resources_only=True)
        max_price = f"${req.max_price:3f}".rstrip("0").rstrip(".") if req.max_price else "-"

        if req.spot is None:
            spot_policy = "auto"
        elif req.spot:
            spot_policy = "spot"
        else:
            spot_policy = "on-demand"

        def th(s: str) -> str:
            return f"[bold]{s}[/bold]"

        props.add_row(th("Project"), self.api.project)
        props.add_row(th("User"), "admin")  # TODO: Get actual user name
        props.add_row(th("Resources"), pretty_req)
        props.add_row(th("Spot policy"), spot_policy)
        props.add_row(th("Max price"), max_price)
        props.add_row(th("Reservation"), run_spec.configuration.reservation or "-")
        if group_by:
            props.add_row(th("Group by"), ", ".join(group_by))

        console.print(props)
        console.print()
