from typing import Optional

from rich.table import Table

from dstack._internal.cli.utils.common import console
from dstack._internal.core.models.instances import InstanceAvailability
from dstack._internal.core.models.runs import RunPlan


def print_run_plan(run_plan: RunPlan, candidates_limit: int = 3):
    job_plan = run_plan.job_plans[0]

    props = Table(box=None, show_header=False)
    props.add_column(no_wrap=True)  # key
    props.add_column()  # value

    req = job_plan.job_spec.requirements
    if req.gpus:
        resources = pretty_format_resources(
            req.cpus,
            req.memory_mib / 1024,
            req.gpus.count,
            req.gpus.name,
            req.gpus.memory_mib / 1024 if req.gpus.memory_mib else None,
        )
    else:
        resources = pretty_format_resources(req.cpus, req.memory_mib / 1024)
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

    if job_plan.job_spec.requirements.spot is None:
        spot_policy = "auto"
    elif job_plan.job_spec.requirements.spot:
        spot_policy = "spot"
    else:
        spot_policy = "on-demand"

    def th(s: str) -> str:
        return f"[bold]{s}[/bold]"

    props.add_row(th("Configuration"), run_plan.run_spec.configuration_path)
    props.add_row(th("Project"), run_plan.project_name)
    props.add_row(th("User"), run_plan.user)
    props.add_row(th("Min resources"), resources)
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
        if r.gpus:
            resources = pretty_format_resources(
                r.cpus,
                r.memory_mib / 1024,
                len(r.gpus),
                r.gpus[0].name,
                r.gpus[0].memory_mib / 1024,
            )
        else:
            resources = pretty_format_resources(r.cpus, r.memory_mib / 1024)
        availability = ""
        if c.availability in {InstanceAvailability.NOT_AVAILABLE, InstanceAvailability.NO_QUOTA}:
            availability = c.availability.value.replace("_", " ").title()
        candidates.add_row(
            f"{i}",
            c.backend,
            c.region,
            c.instance.name,
            resources,
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


def pretty_format_resources(
    cpu: int,
    memory: float,
    gpu_count: Optional[int] = None,
    gpu_name: Optional[str] = None,
    gpu_memory: Optional[float] = None,
) -> str:
    s = f"{cpu}xCPUs, {memory:g}GB"
    if gpu_count:
        s += f", {gpu_count}x{gpu_name or 'GPU'}"
        if gpu_memory:
            s += f" ({gpu_memory:g}GB)"
    return s
