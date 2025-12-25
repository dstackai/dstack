import shutil
from typing import Any, Dict, List, Optional, Union

from rich.markup import escape
from rich.table import Table

from dstack._internal.cli.models.offers import OfferCommandOutput, OfferRequirements
from dstack._internal.cli.models.runs import PsCommandOutput
from dstack._internal.cli.utils.common import (
    NO_FLEETS_WARNING,
    NO_OFFERS_WARNING,
    add_row_from_dict,
    console,
)
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.configurations import DevEnvironmentConfiguration
from dstack._internal.core.models.instances import (
    InstanceAvailability,
    InstanceOfferWithAvailability,
    InstanceType,
)
from dstack._internal.core.models.profiles import (
    DEFAULT_RUN_TERMINATION_IDLE_TIME,
    SpotPolicy,
    TerminationPolicy,
)
from dstack._internal.core.models.runs import (
    Job,
    JobStatus,
    JobSubmission,
    Probe,
    ProbeSpec,
    RunPlan,
    RunStatus,
    get_policy_map,
)
from dstack._internal.core.models.runs import (
    Run as CoreRun,
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

    requirements = OfferRequirements(
        resources=job_plan.job_spec.requirements.resources,
        max_price=job_plan.job_spec.requirements.max_price,
        spot=get_policy_map(run_spec.configuration.spot_policy, default=SpotPolicy.AUTO),
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


def print_runs_json(project: str, runs: List[Run]) -> None:
    """Print runs information in JSON format."""
    output = PsCommandOutput(
        project=project,
        runs=[r._run for r in runs],
    )
    print(output.json())


def print_run_plan(
    run_plan: RunPlan,
    max_offers: Optional[int] = None,
    include_run_properties: bool = True,
    no_fleets: bool = False,
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
        configuration_type = run_spec.configuration.type
        if run_spec.configuration.type == "task":
            configuration_type += f" (nodes={run_spec.configuration.nodes})"
        props.add_row(th("Type"), configuration_type)
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
        console.print(NO_FLEETS_WARNING if no_fleets else NO_OFFERS_WARNING)


def _format_run_status(run) -> str:
    status_text = (
        run.latest_job_submission.status_message
        if run.status.is_finished() and run.latest_job_submission
        else run.status_message
    )
    # Inline of _get_run_status_style
    color_map = {
        RunStatus.PENDING: "white",
        RunStatus.SUBMITTED: "grey",
        RunStatus.PROVISIONING: "deep_sky_blue1",
        RunStatus.RUNNING: "sea_green3",
        RunStatus.TERMINATING: "deep_sky_blue1",
        RunStatus.TERMINATED: "grey",
        RunStatus.FAILED: "indian_red1",
        RunStatus.DONE: "grey",
    }
    if status_text in ("no offers", "interrupted"):
        color = "gold1"
    elif status_text == "no fleets":
        color = "indian_red1"
    elif status_text == "pulling":
        color = "sea_green3"
    else:
        color = color_map.get(run.status, "white")
    status_style = f"bold {color}" if not run.status.is_finished() else color
    return f"[{status_style}]{status_text}[/]"


def _format_job_submission_status(job_submission: JobSubmission, verbose: bool) -> str:
    status_message = job_submission.status_message
    job_status = job_submission.status
    if status_message in ("no offers", "interrupted"):
        color = "gold1"
    elif status_message == "no fleets":
        color = "indian_red1"
    elif status_message == "stopped":
        color = "grey"
    else:
        color_map = {
            JobStatus.SUBMITTED: "grey",
            JobStatus.PROVISIONING: "deep_sky_blue1",
            JobStatus.PULLING: "sea_green3",
            JobStatus.RUNNING: "sea_green3",
            JobStatus.TERMINATING: "deep_sky_blue1",
            JobStatus.TERMINATED: "grey",
            JobStatus.ABORTED: "gold1",
            JobStatus.FAILED: "indian_red1",
            JobStatus.DONE: "grey",
        }
        color = color_map.get(job_status, "white")
    status_style = f"bold {color}" if not job_status.is_finished() else color
    formatted_status_message = f"[{status_style}]{status_message}[/]"
    if verbose and job_submission.inactivity_secs:
        inactive_for = format_duration_multiunit(job_submission.inactivity_secs)
        formatted_status_message += f" (inactive for {inactive_for})"
    return formatted_status_message


def _get_show_deployment_replica_job(run: CoreRun, verbose: bool) -> tuple[bool, bool, bool]:
    show_deployment_num = (
        verbose and run.run_spec.configuration.type == "service"
    ) or run.is_deployment_in_progress()

    replica_nums = {job.job_spec.replica_num for job in run.jobs}
    show_replica = len(replica_nums) > 1

    jobs_by_replica: Dict[int, List[Any]] = {}
    for job in run.jobs:
        replica_num = job.job_spec.replica_num
        if replica_num not in jobs_by_replica:
            jobs_by_replica[replica_num] = []
        jobs_by_replica[replica_num].append(job)

    show_job = any(
        len({j.job_spec.job_num for j in jobs}) > 1 for jobs in jobs_by_replica.values()
    )

    return show_deployment_num, show_replica, show_job


def _format_job_name(
    job: Job,
    latest_job_submission: JobSubmission,
    show_deployment_num: bool,
    show_replica: bool,
    show_job: bool,
) -> str:
    name_parts = []
    if show_replica:
        name_parts.append(f"replica={job.job_spec.replica_num}")
    if show_job:
        name_parts.append(f"job={job.job_spec.job_num}")
    name_suffix = (
        f" deployment={latest_job_submission.deployment_num}" if show_deployment_num else ""
    )
    name_value = "  " + (" ".join(name_parts) if name_parts else "")
    name_value += name_suffix
    return name_value


def _format_price(price: float, is_spot: bool) -> str:
    price_str = f"${price:.4f}".rstrip("0").rstrip(".")
    if is_spot:
        price_str += " (spot)"
    return price_str


def _format_backend(backend_type: BackendType, region: str) -> str:
    backend_str = backend_type.value
    if backend_type == BackendType.REMOTE:
        backend_str = "ssh"
    return f"{backend_str} ({region})"


def _format_instance_type(
    instance_type: InstanceType,
    shared_offer: Optional[InstanceOfferWithAvailability],
    reservation: Optional[str],
) -> str:
    instance_type_str = instance_type.name
    if shared_offer is not None:
        instance_type_str += f" ({shared_offer.blocks}/{shared_offer.total_blocks})"
    if reservation is not None:
        instance_type_str += f" ({reservation})"
    return instance_type_str


def _format_run_name(run: CoreRun, show_deployment_num: bool) -> str:
    parts: List[str] = [run.run_spec.run_name]
    if show_deployment_num:
        parts.append(f" [secondary]deployment={run.deployment_num}[/]")
    return "".join(parts)


def get_runs_table(
    runs: List[Run], verbose: bool = False, format_date: DateFormatter = pretty_date
) -> Table:
    table = Table(box=None, expand=shutil.get_terminal_size(fallback=(120, 40)).columns <= 110)
    table.add_column("NAME", style="bold", no_wrap=True, ratio=2)
    table.add_column("BACKEND", style="grey58", ratio=2)
    if verbose:
        table.add_column("RESOURCES", style="grey58", ratio=3)
        table.add_column("INSTANCE TYPE", style="grey58", no_wrap=True, ratio=1)
    else:
        table.add_column("GPU", ratio=2)
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
        show_deployment_num, show_replica, show_job = _get_show_deployment_replica_job(
            run, verbose
        )
        merge_job_rows = len(run.jobs) == 1 and not show_deployment_num

        run_row: Dict[Union[str, int], Any] = {
            "NAME": _format_run_name(run, show_deployment_num),
            "SUBMITTED": format_date(run.submitted_at),
            "STATUS": _format_run_status(run),
            "RESOURCES": "-",
            "GPU": "-",
            "PRICE": "-",
        }
        if run.error:
            run_row["ERROR"] = run.error
        if not merge_job_rows:
            add_row_from_dict(table, run_row)

        for job in run.jobs:
            latest_job_submission = job.job_submissions[-1]
            status_formatted = _format_job_submission_status(latest_job_submission, verbose)

            job_row: Dict[Union[str, int], Any] = {
                "NAME": _format_job_name(
                    job, latest_job_submission, show_deployment_num, show_replica, show_job
                ),
                "STATUS": status_formatted,
                "PROBES": _format_job_probes(
                    job.job_spec.probes, latest_job_submission.probes, latest_job_submission.status
                ),
                "SUBMITTED": format_date(latest_job_submission.submitted_at),
                "ERROR": latest_job_submission.error,
                "RESOURCES": "-",
                "GPU": "-",
                "PRICE": "-",
            }
            jpd = latest_job_submission.job_provisioning_data
            if jpd is not None:
                shared_offer: Optional[InstanceOfferWithAvailability] = None
                instance_type = jpd.instance_type
                price = jpd.price
                jrd = latest_job_submission.job_runtime_data
                if jrd is not None and jrd.offer is not None and jrd.offer.total_blocks > 1:
                    # We only use offer data from jrd if the job is/was running on a shared
                    # instance (the instance blocks feature). In that case, jpd contains the full
                    # instance offer data, while jrd contains the shared offer (a fraction of
                    # the full offer). Although jrd always contains the offer, we don't use it in
                    # other cases, as, unlike jpd offer data, jrd offer is not updated after
                    # Compute.update_provisioning_data() call, but some backends, namely
                    # Kubernetes, may update offer data via that method.
                    # As long as we don't have a backend which both supports the blocks feature
                    # and may update offer data in update_provisioning_data(), this logic is fine.
                    shared_offer = jrd.offer
                    instance_type = shared_offer.instance
                    price = shared_offer.price
                resources = instance_type.resources
                job_row.update(
                    {
                        "BACKEND": _format_backend(jpd.backend, jpd.region),
                        "RESOURCES": resources.pretty_format(include_spot=False),
                        "GPU": resources.pretty_format(gpu_only=True, include_spot=False),
                        "INSTANCE TYPE": _format_instance_type(
                            instance_type, shared_offer, jpd.reservation
                        ),
                        "PRICE": _format_price(price, resources.spot),
                    }
                )
            if merge_job_rows:
                _status = job_row["STATUS"]
                _resources = job_row["RESOURCES"]
                _gpu = job_row["GPU"]
                _price = job_row["PRICE"]
                job_row.update(run_row)
                job_row["RESOURCES"] = _resources
                job_row["GPU"] = _gpu
                job_row["PRICE"] = _price
                job_row["STATUS"] = _status
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
