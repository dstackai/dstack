"""Table rendering for `dstack metrics`."""

from datetime import datetime
from typing import Any, List, Optional

from rich.console import RenderableType
from rich.table import Table
from rich.text import Text

from dstack._internal.cli.utils.common import console
from dstack._internal.cli.utils.sparkline import (
    GPU_RAMP,
    HOST_RAMP,
    Ramp,
    no_data,
    sparkline,
    supports_unicode,
)
from dstack._internal.core.models.instances import Resources
from dstack._internal.core.models.metrics import JobMetrics
from dstack._internal.core.models.runs import Job
from dstack._internal.utils.common import pretty_date

MAX_SAMPLES = 1000
"""How many samples to request, matching the UI.

A sample count rather than a time window: at the server's ~10s cadence this outruns the
hour of metrics a running job retains, so the response always holds everything there is.
A fixed window would under-fill for a run younger than the window.
"""

WATCH_INTERVAL_SECONDS = 10
"""How often `--watch` re-fetches.

Matched to the server's collection cadence, which is a 10s interval plus a 9s per-job
guard, so a new point cannot arrive faster than this. Not `LIVE_TABLE_PROVISION_INTERVAL_SECS`
(2s), which is short because provisioning state genuinely does change that fast.
"""

MIN_SPARK_WIDTH = 10
MAX_SPARK_WIDTH = 80
_FIXED_COLUMNS = 34
"""Columns the table needs besides the sparklines: labels, numbers and padding."""

_SPARKLINE_COLUMNS = 2
"""UTILIZATION and MEMORY, reused by every row, so a cell costs two columns."""


def _spark_width(console_width: int) -> int:
    """How many cells fit. An hour in ten cells is six minutes each, which averages away
    everything but the broadest shape, so the sparklines take whatever slack there is."""
    budget = console_width - _FIXED_COLUMNS
    return max(MIN_SPARK_WIDTH, min(MAX_SPARK_WIDTH, budget // _SPARKLINE_COLUMNS))


def get_metrics_table(
    job: Job, metrics: JobMetrics, console_width: Optional[int] = None
) -> RenderableType:
    """One row per resource, with `UTILIZATION` and `MEMORY` reused by all of them.

    `cpu` contributes the host's utilization and system RAM, `gpu=N` the device's
    utilization and HBM: the label names the processor and the column gives that
    processor's memory. Four dedicated columns instead would leave half of every row empty
    and cost twice as much width per sparkline cell.

    One job, like `dstack logs` -- the endpoint is per-job, and so is the UI's metrics page.
    """
    ascii_only = not supports_unicode(console)
    resources = _get_resources(job)
    width = _spark_width(console_width or console.width)

    table = Table(box=None)
    # no header: every cell in this column already reads `cpu` or `gpu=N`
    table.add_column("", style="secondary", no_wrap=True)
    table.add_column("UTILIZATION", no_wrap=True)
    table.add_column("MEMORY", no_wrap=True)

    table.add_row(
        "cpu",
        _cpu_cell(metrics, resources, width, ascii_only),
        _memory_cell(metrics, resources, width, ascii_only),
    )
    table.add_row("", "", "")  # host and devices are different things; separate them
    for index in range(_gpus_num(metrics, resources)):
        table.add_row(
            f"gpu={index}",
            _gpu_util_cell(metrics, index, width, ascii_only),
            _gpu_memory_cell(metrics, resources, index, width, ascii_only),
        )
    window = _window(metrics)
    if window is not None:
        axis = _axis(width, *window)
        table.add_row("", "", "")
        table.add_row("", axis, axis)
    return table


# ---------------------------------------------------------------------- cells


def _cpu_cell(
    job_metrics: JobMetrics, resources: Optional[Resources], width: int, ascii_only: bool
) -> Text:
    values = _metric_values(job_metrics, "cpu_usage_percent")
    if not values:
        return no_data()
    cpus = resources.cpus if resources else None
    if cpus:
        values = [v / cpus for v in values]
    label = f"{values[-1]:.0f}%"
    if cpus:
        label += f" of {cpus}"
    return _cell(sparkline(values, width, HOST_RAMP, ascii_only=ascii_only), label)


def _memory_cell(
    job_metrics: JobMetrics, resources: Optional[Resources], width: int, ascii_only: bool
) -> Text:
    values = _metric_values(job_metrics, "memory_working_set_bytes")
    if not values:
        return no_data()
    total = resources.memory_mib * 1024 * 1024 if resources else None
    return _level_cell(values, total, width, ascii_only, HOST_RAMP)


def _gpu_memory_cell(
    job_metrics: JobMetrics,
    resources: Optional[Resources],
    index: int,
    width: int,
    ascii_only: bool,
) -> Text:
    values = _metric_values(job_metrics, f"gpu_memory_usage_bytes_gpu{index}")
    if not values:
        return no_data()
    total = None
    if resources and index < len(resources.gpus):
        total = resources.gpus[index].memory_mib * 1024 * 1024
    return _level_cell(values, total, width, ascii_only, GPU_RAMP)


def _gpu_util_cell(job_metrics: JobMetrics, index: int, width: int, ascii_only: bool) -> Text:
    values = _metric_values(job_metrics, f"gpu_util_percent_gpu{index}")
    if not values:
        return no_data()
    return _cell(sparkline(values, width, GPU_RAMP, ascii_only=ascii_only), f"{values[-1]:.0f}%")


def _level_cell(
    values: List[float], total: Optional[float], width: int, ascii_only: bool, ramp: Ramp
) -> Text:
    """Memory: fraction of capacity, plus used/total in GB."""
    percents = [v / total * 100 for v in values] if total else values
    label = format_memory(values[-1], 0)
    if total:
        label += f"/{format_memory(total, 0)}"
    return _cell(sparkline(percents, width, ramp, ascii_only=ascii_only), label)


def _cell(spark: Text, label: str) -> Text:
    """A sparkline is never the only place a value lives -- its number sits beside it.

    The number is unstyled: colouring it repeats what the sparkline's colour already says,
    and there is nothing green or grey about a string like `0MB/80GB`.
    """
    return Text.assemble(spark, " ", label)


# ----------------------------------------------------------------------- data


def _axis(width: int, first: datetime, last: datetime) -> Text:
    """A labelled rule exactly as wide as the sparkline above it, so the two align."""
    left, right = _stamp(first), _stamp(last)
    fill = max(1, width - len(left) - len(right) - 2)
    return Text(f"{left} " + "─" * fill + f" {right}", style="grey42")


def _stamp(moment: datetime) -> str:
    """`now` for the newest sample of a running job, an absolute local time otherwise.

    Collection runs every ~10s, so a running job's newest sample is always within
    `pretty_date`'s `now` threshold; anything else is old enough to deserve a real time,
    and a finished run then cannot be mistaken for live data.
    """
    if pretty_date(moment) == "now":
        return "now"
    local = moment.astimezone()
    return f"{local.day} {local:%b %H:%M}"


def _window(job_metrics: JobMetrics) -> Optional[tuple[datetime, datetime]]:
    """Oldest and newest sample, or None if there are none."""
    stamps = [t for metric in job_metrics.metrics for t in metric.timestamps]
    return (min(stamps), max(stamps)) if stamps else None


def _metric_values(job_metrics: JobMetrics, name: str) -> List[Any]:
    """Values for `name`, oldest first.

    The server returns points ordered latest to earliest. Reversing here, once, at the
    boundary, is what keeps every sparkline drawn downstream running left-to-right in time.
    """
    for metric in job_metrics.metrics:
        if metric.name == name:
            return list(reversed(metric.values))
    return []


def _latest(job_metrics: JobMetrics, name: str) -> Optional[Any]:
    values = _metric_values(job_metrics, name)
    return values[-1] if values else None


def _gpus_num(job_metrics: JobMetrics, resources: Optional[Resources]) -> int:
    """How many device rows to print.

    Prefer the offer over the metrics: it is still known when no samples have arrived, and
    when the server drops GPU metrics because the device count changed mid-window.
    """
    if resources is not None and resources.gpus:
        return len(resources.gpus)
    detected = _latest(job_metrics, "gpus_detected_num")
    return int(detected) if detected else 0


def _get_resources(job: Job) -> Optional[Resources]:
    submission = job.job_submissions[-1]
    jrd = submission.job_runtime_data
    if jrd is not None and jrd.offer is not None:
        return jrd.offer.instance.resources
    jpd = submission.job_provisioning_data
    if jpd is not None:
        return jpd.instance_type.resources
    return None


def format_memory(memory_bytes: float, decimal_places: int) -> str:
    """See test_format_memory in tests/_internal/cli/commands/test_metrics.py for examples."""
    memory_mb = memory_bytes / 1024 / 1024
    if memory_mb >= 1024:
        value = memory_mb / 1024
        unit = "GB"
    else:
        value = memory_mb
        unit = "MB"

    if decimal_places == 0:
        return f"{round(value)}{unit}"
    return f"{value:.{decimal_places}f}".rstrip("0").rstrip(".") + unit
