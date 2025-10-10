import shutil
from typing import Any, Dict, List, Optional, Union

from rich.markup import escape
from rich.table import Table

from dstack._internal.cli.utils.common import NO_OFFERS_WARNING, add_row_from_dict, console
from dstack._internal.core.models.configurations import DevEnvironmentConfiguration
from dstack._internal.core.models.instances import InstanceAvailability
from dstack._internal.core.models.profiles import (
    DEFAULT_RUN_TERMINATION_IDLE_TIME,
    TerminationPolicy,
)
from dstack._internal.core.models.runs import (
    JobStatus,
    Probe,
    ProbeSpec,
    RunPlan,
)
from dstack._internal.core.services.profiles import get_termination
from dstack._internal.utils.common import (
    DateFormatter,
    batched,
    format_duration_multiunit,
    format_pretty_duration,
    pretty_date,
)
from dstack.api import Run


def print_offers_json(run_plan: RunPlan, run_spec):
    """Print offers information in JSON format."""
    job_plan = run_plan.job_plans[0]

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
                "backend": ("ssh" if offer.backend.value == "remote" else offer.backend.value),
                "region": offer.region,
                "instance_type": offer.instance.name,
                "resources": offer.instance.resources.dict(),
                "spot": offer.instance.resources.spot,
                "price": float(offer.price),
                "availability": offer.availability.value,
            }
        )

    import json

    print(json.dumps(output, indent=2))


def print_run_plan(
    run_plan: RunPlan, max_offers: Optional[int] = None, include_run_properties: bool = True
):
    run_spec = run_plan.get_effective_run_spec()
    job_plan = run_plan.job_plans[0]

    props = Table(box=None, show_header=False)
    props.add_column(no_wrap=True)  # key
    props.add_column()  # value

    req = job_plan.job_spec.requirements
    pretty_req = req.pretty_format(resources_only=True)
    max_price = f"${req.max_price:3f}".rstrip("0").rstrip(".") if req.max_price else "-"
    max_duration = (
        format_pretty_duration(job_plan.job_spec.max_duration)
        if job_plan.job_spec.max_duration
        else "-"
    )
    if include_run_properties:
        inactivity_duration = None
        if isinstance(run_spec.configuration, DevEnvironmentConfiguration):
            inactivity_duration = "-"
            if isinstance(run_spec.configuration.inactivity_duration, int):
                inactivity_duration = format_pretty_duration(
                    run_spec.configuration.inactivity_duration
                )
        if job_plan.job_spec.retry is None:
            retry = "-"
        else:
            retry = escape(job_plan.job_spec.retry.pretty_format())

        profile = run_spec.merged_profile
        creation_policy = profile.creation_policy
        # FIXME: This assumes the default idle_duration is the same for client and server.
        # If the server changes idle_duration, old clients will see incorrect value.
        termination_policy, termination_idle_time = get_termination(
            profile, DEFAULT_RUN_TERMINATION_IDLE_TIME
        )
        if termination_policy == TerminationPolicy.DONT_DESTROY:
            idle_duration = "-"
        else:
            idle_duration = format_pretty_duration(termination_idle_time)

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
    if include_run_properties:
        props.add_row(th("Configuration"), run_spec.configuration_path)
        props.add_row(th("Type"), run_spec.configuration.type)
    props.add_row(th("Resources"), pretty_req)
    props.add_row(th("Spot policy"), spot_policy)
    props.add_row(th("Max price"), max_price)
    if include_run_properties:
        props.add_row(th("Retry policy"), retry)
        props.add_row(th("Creation policy"), creation_policy)
        props.add_row(th("Idle duration"), idle_duration)
        props.add_row(th("Max duration"), max_duration)
        if inactivity_duration is not None:  # None means n/a
            props.add_row(th("Inactivity duration"), inactivity_duration)
    props.add_row(th("Reservation"), run_spec.configuration.reservation or "-")

    offers = Table(box=None, expand=shutil.get_terminal_size(fallback=(120, 40)).columns <= 110)
    offers.add_column("#")
    offers.add_column("BACKEND", style="grey58", ratio=2)
    offers.add_column("RESOURCES", ratio=4)
    offers.add_column("INSTANCE TYPE", style="grey58", no_wrap=True, ratio=2)
    offers.add_column("PRICE", style="grey58", ratio=1)
    offers.add_column()

    job_plan.offers = job_plan.offers[:max_offers] if max_offers else job_plan.offers

    for i, offer in enumerate(job_plan.offers, start=1):
        r = offer.instance.resources

        availability = ""
        if offer.availability in {
            InstanceAvailability.NOT_AVAILABLE,
            InstanceAvailability.NO_QUOTA,
            InstanceAvailability.IDLE,
            InstanceAvailability.BUSY,
        }:
            availability = offer.availability.value.replace("_", " ").lower()
        instance = offer.instance.name
        if offer.total_blocks > 1:
            instance += f" ({offer.blocks}/{offer.total_blocks})"
        offers.add_row(
            f"{i}",
            offer.backend.replace("remote", "ssh") + " (" + offer.region + ")",
            r.pretty_format(include_spot=True),
            instance,
            f"${offer.price:.4f}".rstrip("0").rstrip("."),
            availability,
            style=None if i == 1 or not include_run_properties else "secondary",
        )
    if job_plan.total_offers > len(job_plan.offers):
        offers.add_row("", "...", style="secondary")

    console.print(props)
    console.print()
    if len(job_plan.offers) > 0:
        console.print(offers)
        if job_plan.total_offers > len(job_plan.offers):
            console.print(
                f"[secondary] Shown {len(job_plan.offers)} of {job_plan.total_offers} offers, "
                f"${job_plan.max_price:3f}".rstrip("0").rstrip(".")
                + "max[/]"
            )
        console.print()
    else:
        console.print(NO_OFFERS_WARNING)


def get_runs_table(
    runs: List[Run], verbose: bool = False, format_date: DateFormatter = pretty_date
) -> Table:
    table = Table(box=None, expand=shutil.get_terminal_size(fallback=(120, 40)).columns <= 110)
    table.add_column("NAME", style="bold", no_wrap=True, ratio=2)
    table.add_column("BACKEND", style="grey58", ratio=2)
    table.add_column("RESOURCES", ratio=3 if not verbose else 2)
    if verbose:
        table.add_column("INSTANCE TYPE", no_wrap=True, ratio=1)
    table.add_column("PRICE", style="grey58", ratio=1)
    table.add_column("STATUS", no_wrap=True, ratio=1)
    if verbose or any(
        run._run.is_deployment_in_progress()
        and any(job.job_submissions[-1].probes for job in run._run.jobs)
        for run in runs
    ):
        table.add_column("PROBES", ratio=1)
    table.add_column("SUBMITTED", style="grey58", no_wrap=True, ratio=1)
    if verbose:
        table.add_column("ERROR", no_wrap=True, ratio=2)

    for run in runs:
        run = run._run  # TODO(egor-s): make public attribute
        show_deployment_num = (
            verbose
            and run.run_spec.configuration.type == "service"
            or run.is_deployment_in_progress()
        )
        merge_job_rows = len(run.jobs) == 1 and not show_deployment_num

        run_row: Dict[Union[str, int], Any] = {
            "NAME": run.run_spec.run_name
            + (f" [secondary]deployment={run.deployment_num}[/]" if show_deployment_num else ""),
            "SUBMITTED": format_date(run.submitted_at),
            "STATUS": (
                run.latest_job_submission.status_message
                if run.status.is_finished() and run.latest_job_submission
                else run.status_message
            ),
        }
        if run.error:
            run_row["ERROR"] = run.error
        if not merge_job_rows:
            add_row_from_dict(table, run_row)

        for job in run.jobs:
            latest_job_submission = job.job_submissions[-1]
            status = latest_job_submission.status.value
            if verbose and latest_job_submission.inactivity_secs:
                inactive_for = format_duration_multiunit(latest_job_submission.inactivity_secs)
                status += f" (inactive for {inactive_for})"
            job_row: Dict[Union[str, int], Any] = {
                "NAME": f"  replica={job.job_spec.replica_num} job={job.job_spec.job_num}"
                + (
                    f" deployment={latest_job_submission.deployment_num}"
                    if show_deployment_num
                    else ""
                ),
                "STATUS": latest_job_submission.status_message,
                "PROBES": _format_job_probes(
                    job.job_spec.probes, latest_job_submission.probes, latest_job_submission.status
                ),
                "SUBMITTED": format_date(latest_job_submission.submitted_at),
                "ERROR": latest_job_submission.error,
            }
            jpd = latest_job_submission.job_provisioning_data
            if jpd is not None:
                resources = jpd.instance_type.resources
                instance_type = jpd.instance_type.name
                jrd = latest_job_submission.job_runtime_data
                if jrd is not None and jrd.offer is not None:
                    resources = jrd.offer.instance.resources
                    if jrd.offer.total_blocks > 1:
                        instance_type += f" ({jrd.offer.blocks}/{jrd.offer.total_blocks})"
                if jpd.reservation:
                    instance_type += f" ({jpd.reservation})"
                job_row.update(
                    {
                        "BACKEND": f"{jpd.backend.value.replace('remote', 'ssh')} ({jpd.region})",
                        "RESOURCES": resources.pretty_format(include_spot=True),
                        "INSTANCE TYPE": instance_type,
                        "PRICE": f"${jpd.price:.4f}".rstrip("0").rstrip("."),
                    }
                )
            if merge_job_rows:
                # merge rows
                job_row.update(run_row)
            add_row_from_dict(table, job_row, style="secondary" if len(run.jobs) != 1 else None)

    return table


def _format_job_probes(
    probe_specs: list[ProbeSpec], probes: list[Probe], job_status: JobStatus
) -> str:
    if not probes or job_status != JobStatus.RUNNING:
        return ""
    statuses = []
    for probe_spec, probe in zip(probe_specs, probes):
        # NOTE: the symbols are documented in concepts/services.md, keep in sync.
        if probe.success_streak >= probe_spec.ready_after:
            status = "[code]✓[/]"
        elif probe.success_streak > 0:
            status = "[warning]~[/]"
        else:
            status = "[error]×[/]"
        statuses.append(status)
    # split into whitespace-delimited batches to allow column wrapping
    return " ".join("".join(batch) for batch in batched(statuses, 5))
