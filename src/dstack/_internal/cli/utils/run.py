from typing import List, Optional

from rich.markup import escape
from rich.table import Table

from dstack._internal.cli.utils.common import add_row_from_dict, console
from dstack._internal.core.models.instances import InstanceAvailability
from dstack._internal.core.models.profiles import TerminationPolicy
from dstack._internal.core.models.runs import (
    Job,
    JobTerminationReason,
    RunPlan,
    RunTerminationReason,
)
from dstack._internal.utils.common import format_pretty_duration, pretty_date
from dstack.api import Run


def print_run_plan(run_plan: RunPlan, offers_limit: int = 3):
    job_plan = run_plan.job_plans[0]

    props = Table(box=None, show_header=False)
    props.add_column(no_wrap=True)  # key
    props.add_column()  # value

    req = job_plan.job_spec.requirements
    pretty_req = req.pretty_format(resources_only=True)
    max_price = f"${req.max_price:g}" if req.max_price else "-"
    max_duration = (
        f"{job_plan.job_spec.max_duration / 3600:g}h" if job_plan.job_spec.max_duration else "-"
    )
    if job_plan.job_spec.retry is None:
        retry = "no"
    else:
        retry = escape(job_plan.job_spec.retry.pretty_format())

    profile = run_plan.run_spec.merged_profile
    creation_policy = profile.creation_policy
    termination_policy = profile.termination_policy
    if termination_policy == TerminationPolicy.DONT_DESTROY:
        termination_idle_time = "-"
    else:
        termination_idle_time = format_pretty_duration(profile.termination_idle_time)

    if req.spot is None:
        spot_policy = "auto"
    elif req.spot:
        spot_policy = "spot"
    else:
        spot_policy = "on-demand"

    def th(s: str) -> str:
        return f"[bold]{s}[/bold]"

    props.add_row(th("Configuration"), run_plan.run_spec.configuration_path)
    props.add_row(th("Project"), run_plan.project_name)
    props.add_row(th("User"), run_plan.user)
    props.add_row(th("Pool"), profile.pool_name)
    props.add_row(th("Min resources"), pretty_req)
    props.add_row(th("Max price"), max_price)
    props.add_row(th("Max duration"), max_duration)
    props.add_row(th("Spot policy"), spot_policy)
    props.add_row(th("Retry policy"), retry)
    props.add_row(th("Creation policy"), creation_policy)
    props.add_row(th("Termination policy"), termination_policy)
    props.add_row(th("Termination idle time"), termination_idle_time)

    offers = Table(box=None)
    offers.add_column("#")
    offers.add_column("BACKEND")
    offers.add_column("REGION")
    offers.add_column("INSTANCE")
    offers.add_column("RESOURCES")
    offers.add_column("SPOT")
    offers.add_column("PRICE")
    offers.add_column()

    job_plan.offers = job_plan.offers[:offers_limit]

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
        offers.add_row(
            f"{i}",
            offer.backend.replace("remote", "ssh"),
            offer.region,
            offer.instance.name,
            r.pretty_format(),
            "yes" if r.spot else "no",
            f"${offer.price:g}",
            availability,
            style=None if i == 1 else "secondary",
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
                f"${job_plan.max_price:g} max[/]"
            )
        console.print()


def generate_runs_table(
    runs: List[Run], include_configuration: bool = False, verbose: bool = False
) -> Table:
    table = Table(box=None)
    table.add_column("NAME", style="bold", no_wrap=True)
    if include_configuration:
        table.add_column("CONFIGURATION", style="grey58")
    table.add_column("BACKEND", style="grey58", no_wrap=True, max_width=16)
    table.add_column("REGION", style="grey58")
    if verbose:
        table.add_column("INSTANCE", no_wrap=True)
    table.add_column("RESOURCES")
    table.add_column("SPOT")
    table.add_column("PRICE", no_wrap=True)
    table.add_column("STATUS", no_wrap=True)
    table.add_column("SUBMITTED", style="grey58", no_wrap=True)
    if verbose:
        table.add_column("ERROR", no_wrap=True)

    for run in runs:
        run_error = _get_run_error(run)
        run = run._run  # TODO(egor-s): make public attribute

        run_row = {
            "NAME": run.run_spec.run_name,
            "CONFIGURATION": run.run_spec.configuration_path,
            "STATUS": run.status,
            "SUBMITTED": pretty_date(run.submitted_at),
            "ERROR": run_error,
        }
        if len(run.jobs) != 1:
            add_row_from_dict(table, run_row)

        for job in run.jobs:
            job_row = {
                "NAME": f"  replica {job.job_spec.replica_num}\n  job_num {job.job_spec.job_num}",
                "STATUS": job.job_submissions[-1].status,
                "SUBMITTED": pretty_date(job.job_submissions[-1].submitted_at),
                "ERROR": _get_job_error(job),
            }
            jpd = job.job_submissions[-1].job_provisioning_data
            if jpd is not None:
                job_row.update(
                    {
                        "BACKEND": jpd.backend.value.replace("remote", "ssh"),
                        "REGION": jpd.region,
                        "INSTANCE": jpd.instance_type.name,
                        "RESOURCES": jpd.instance_type.resources.pretty_format(),
                        "SPOT": "yes" if jpd.instance_type.resources.spot else "no",
                        "PRICE": f"${jpd.price:.4}",
                    }
                )
            if len(run.jobs) == 1:
                # merge rows
                job_row.update(run_row)
            add_row_from_dict(table, job_row, style="secondary" if len(run.jobs) != 1 else None)

    return table


def _get_run_error(run: Run) -> str:
    if run._run.termination_reason is None:
        return ""
    if len(run._run.jobs) > 1:
        return run._run.termination_reason.name
    run_job_termination_reason = _get_run_job_termination_reason(run)
    # For failed runs, also show termination reason to provide more context.
    # For other run statuses, the job termination reason will duplicate run status.
    if run_job_termination_reason is not None and run._run.termination_reason in [
        RunTerminationReason.JOB_FAILED,
        RunTerminationReason.SERVER_ERROR,
        RunTerminationReason.RETRY_LIMIT_EXCEEDED,
    ]:
        return f"{run._run.termination_reason.name}\n({run_job_termination_reason.name})"
    return run._run.termination_reason.name


def _get_run_job_termination_reason(run: Run) -> Optional[JobTerminationReason]:
    for job in run._run.jobs:
        if len(job.job_submissions) > 0:
            if job.job_submissions[-1].termination_reason is not None:
                return job.job_submissions[-1].termination_reason
    return None


def _get_job_error(job: Job) -> str:
    if job.job_submissions[-1].termination_reason is None:
        return ""
    return job.job_submissions[-1].termination_reason.name
