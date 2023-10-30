from typing import List, Optional

from rich.table import Table

from dstack._internal.cli.utils.common import console
from dstack._internal.core.models.instances import InstanceAvailability, InstanceType, Resources
from dstack._internal.core.models.runs import RunPlan
from dstack._internal.utils.common import pretty_date
from dstack.api import Run


def print_run_plan(run_plan: RunPlan, candidates_limit: int = 3):
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
    retry_policy = job_plan.job_spec.retry_policy
    retry_policy = (
        (f"{retry_policy.limit / 3600:g}h" if retry_policy.limit else "yes")
        if retry_policy.retry
        else "no"
    )

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
    props.add_row(th("Min resources"), pretty_req)
    props.add_row(th("Max price"), max_price)
    props.add_row(th("Max duration"), max_duration)
    props.add_row(th("Spot policy"), spot_policy)
    props.add_row(th("Retry policy"), retry_policy)

    candidates = Table(box=None)
    candidates.add_column("#")
    candidates.add_column("BACKEND")
    candidates.add_column("REGION")
    candidates.add_column("INSTANCE")
    candidates.add_column("RESOURCES")
    candidates.add_column("SPOT")
    candidates.add_column("PRICE")
    candidates.add_column()

    job_plan.candidates = job_plan.candidates[:candidates_limit]

    for i, c in enumerate(job_plan.candidates, start=1):
        r = c.instance.resources

        availability = ""
        if c.availability in {InstanceAvailability.NOT_AVAILABLE, InstanceAvailability.NO_QUOTA}:
            availability = c.availability.value.replace("_", " ").title()
        candidates.add_row(
            f"{i}",
            c.backend,
            c.region,
            c.instance.name,
            r.pretty_format(),
            "yes" if r.spot else "no",
            f"${c.price:g}",
            availability,
            style=None if i == 1 else "grey58",
        )
    if len(job_plan.candidates) == candidates_limit:
        candidates.add_row("", "...", style="grey58")

    console.print(props)
    console.print()
    if len(job_plan.candidates) > 0:
        console.print(candidates)
        console.print()


def generate_runs_table(
    runs: List[Run], include_configuration: bool = False, verbose: bool = False
) -> Table:
    table = Table(box=None)
    table.add_column("RUN", style="bold", no_wrap=True)
    if include_configuration:
        table.add_column("CONFIGURATION", style="grey58")
    table.add_column("USER", style="grey58", no_wrap=True, max_width=16)
    table.add_column("BACKEND", style="grey58", no_wrap=True, max_width=16)
    if verbose:
        table.add_column("INSTANCE", no_wrap=True)
    table.add_column("RESOURCES")
    table.add_column("SPOT", no_wrap=True)
    table.add_column("PRICE", no_wrap=True)
    table.add_column("STATUS", no_wrap=True)
    table.add_column("SUBMITTED", style="grey58", no_wrap=True)
    if verbose:
        table.add_column("ERROR", no_wrap=True)

    for run in runs:
        run = run._run  # TODO
        job = run.jobs[0]  # TODO
        provisioning = job.job_submissions[-1].job_provisioning_data  # TODO

        renderables = [run.run_spec.run_name]
        if include_configuration:
            renderables.append(run.run_spec.configuration_path)
        renderables += [
            run.user,
            provisioning.backend.value if provisioning else "",
            *_render_instance_and_resources(
                provisioning.instance_type if provisioning else None, verbose
            ),
            ("yes" if provisioning.instance_type.resources.spot else "no") if provisioning else "",
            f"{provisioning.price:.4}$" if provisioning else "",
            run.status,
            pretty_date(run.submitted_at),
        ]
        if verbose:
            renderables.append("TODO")  # TODO
        table.add_row(*renderables)
    return table


def _render_instance_and_resources(instance: Optional[InstanceType], verbose: bool) -> List[str]:
    if not instance:
        return [""] if not verbose else ["", ""]
    rows = [] if not verbose else [instance.name]
    rows.append(instance.resources.pretty_format())
    return rows
