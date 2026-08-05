from datetime import datetime
from typing import Any, List, Optional

from rich.console import RenderableType
from rich.table import Table
from rich.text import Text

from dstack._internal.cli.utils.common import console
from dstack._internal.cli.utils.sparkline import GPU_RAMP, HOST_RAMP, Ramp, no_data, sparkline
from dstack._internal.core.models.instances import Resources
from dstack._internal.core.models.metrics import JobMetrics
from dstack._internal.core.models.runs import Job
from dstack._internal.utils.common import pretty_date

MAX_SAMPLES = 1000
"""A sample count, not a window: outruns the hour a running job retains, so a young run is
never under-filled. Matches the UI."""

WATCH_INTERVAL_SECONDS = 10
"""Matched to the server's collection cadence; a new point cannot arrive faster."""

MIN_SPARK_WIDTH = 10
MAX_SPARK_WIDTH = 80

AXIS_RULE = "┄"
_FIXED_COLUMNS = 34
"""Labels, numbers and padding. Hand-measured against a `589GB/1480GB`-sized label; a
wider one (a 2000GB host prints `1218GB/2000GB`) overflows and Rich ellipsizes the row
labels rather than shrinking the sparklines."""

_SPARKLINE_COLUMNS = 2


def _spark_width(console_width: int) -> int:
    budget = console_width - _FIXED_COLUMNS
    return max(MIN_SPARK_WIDTH, min(MAX_SPARK_WIDTH, budget // _SPARKLINE_COLUMNS))


def get_metrics_table(
    job: Job, metrics: JobMetrics, console_width: Optional[int] = None
) -> RenderableType:
    resources = _get_resources(job)
    width = _spark_width(console_width or console.width)

    table = Table(box=None)
    # no header: every cell in this column already reads `cpu` or `gpu=N`
    table.add_column("", style="secondary", no_wrap=True)
    table.add_column("UTILIZATION", no_wrap=True)
    table.add_column("MEMORY", no_wrap=True)

    table.add_row(
        "cpu",
        _cpu_cell(metrics, resources, width),
        _memory_cell(metrics, resources, width),
    )
    table.add_row("", "", "")  # host and devices are different things; separate them
    for index in range(_gpus_num(metrics, resources)):
        table.add_row(
            f"gpu={index}",
            _gpu_util_cell(metrics, index, width),
            _gpu_memory_cell(metrics, resources, index, width),
        )
    window = _window(metrics)
    if window is not None:
        axis = _axis(min(width, _samples_num(metrics)), *window)
        table.add_row("", "", "")
        table.add_row("", axis, axis)
    return table


def _cpu_cell(job_metrics: JobMetrics, resources: Optional[Resources], width: int) -> Text:
    values = _metric_values(job_metrics, "cpu_usage_percent")
    if not values:
        return no_data()
    cpus = resources.cpus if resources else None
    if cpus:
        values = [v / cpus for v in values]
    label = f"{values[-1]:.0f}%"
    if cpus:
        label += f" of {cpus}"
    return _cell(sparkline(values, width, HOST_RAMP), label)


def _memory_cell(job_metrics: JobMetrics, resources: Optional[Resources], width: int) -> Text:
    values = _metric_values(job_metrics, "memory_working_set_bytes")
    if not values:
        return no_data()
    total = resources.memory_mib * 1024 * 1024 if resources else None
    return _level_cell(values, total, width, HOST_RAMP)


def _gpu_memory_cell(
    job_metrics: JobMetrics,
    resources: Optional[Resources],
    index: int,
    width: int,
) -> Text:
    values = _metric_values(job_metrics, f"gpu_memory_usage_bytes_gpu{index}")
    if not values:
        return no_data()
    total = None
    if resources and index < len(resources.gpus):
        total = resources.gpus[index].memory_mib * 1024 * 1024
    return _level_cell(values, total, width, GPU_RAMP)


def _gpu_util_cell(job_metrics: JobMetrics, index: int, width: int) -> Text:
    values = _metric_values(job_metrics, f"gpu_util_percent_gpu{index}")
    if not values:
        return no_data()
    return _cell(sparkline(values, width, GPU_RAMP), f"{values[-1]:.0f}%")


def _level_cell(values: List[float], total: Optional[float], width: int, ramp: Ramp) -> Text:
    percents = [v / total * 100 for v in values] if total else values
    label = format_memory(values[-1], 0)
    if total:
        label += f"/{format_memory(total, 0)}"
    return _cell(sparkline(percents, width, ramp), label)


def _cell(spark: Text, label: str) -> Text:
    return Text.assemble(spark, " ", label)


def _axis(width: int, first: datetime, last: datetime) -> Text:
    """`<oldest> ┄┄┄ <newest>`, never wider than the sparkline above it.

    The rule is what pairs the two stamps. UTILIZATION and MEMORY each print one, so the
    row ends up holding four times, and with the rule left blank the only cue is spacing --
    which points the wrong way above 88 columns: at 200 there are 66 blanks between a
    column's own two stamps but only 13 between the columns, so each column's newest time
    reads as belonging to the next column's oldest.

    A run draws one cell per sample, so for its first few minutes there are fewer cells
    than two dates need. Dropping the date keeps the axis inside its cell; overflowing
    instead widens the column and pulls MEMORY out of line with the charts.
    """
    left, right = _stamp(first), _stamp(last)
    if len(left) + len(right) + 3 > width:
        left, right = _stamp(first, clock_only=True), _stamp(last, clock_only=True)
    if len(left) + len(right) + 2 > width:
        return Text("")
    fill = width - len(left) - len(right) - 2
    return Text(f"{left} " + AXIS_RULE * fill + f" {right}", style="grey42")


def _stamp(moment: datetime, clock_only: bool = False) -> str:
    if pretty_date(moment) == "now":
        return "now"
    local = moment.astimezone()
    return f"{local:%H:%M}" if clock_only else f"{local.day} {local:%b %H:%M}"


def _window(job_metrics: JobMetrics) -> Optional[tuple[datetime, datetime]]:
    stamps = [t for metric in job_metrics.metrics for t in metric.timestamps]
    return (min(stamps), max(stamps)) if stamps else None


def _samples_num(job_metrics: JobMetrics) -> int:
    """`slices` never draws more cells than it has samples, so the axis must stop there
    too -- else it claims a span nothing was measured over, and Rich widens the column."""
    return max((len(metric.timestamps) for metric in job_metrics.metrics), default=0)


def _metric_values(job_metrics: JobMetrics, name: str) -> List[Any]:
    """Values for `name`, oldest first. The server sends latest-first; reversing here, once,
    is what keeps every sparkline downstream running left-to-right in time."""
    for metric in job_metrics.metrics:
        if metric.name == name:
            return list(reversed(metric.values))
    return []


def _latest(job_metrics: JobMetrics, name: str) -> Optional[Any]:
    values = _metric_values(job_metrics, name)
    return values[-1] if values else None


def _gpus_num(job_metrics: JobMetrics, resources: Optional[Resources]) -> int:
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
