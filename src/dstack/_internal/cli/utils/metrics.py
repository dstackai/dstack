from datetime import datetime, timedelta, timezone
from typing import Any, List, Optional, Sequence

from rich.console import RenderableType
from rich.table import Table
from rich.text import Text

from dstack._internal.cli.utils.common import console
from dstack._internal.cli.utils.sparkline import GPU_RAMP, HOST_RAMP, Ramp, no_data, sparkline
from dstack._internal.core.models.instances import Resources
from dstack._internal.core.models.metrics import JobMetrics
from dstack._internal.core.models.runs import Job

MAX_SAMPLES = 1000
"""A sample count, not a window: outruns the hour a running job retains, so a young run is
never under-filled. Matches the UI."""

WATCH_INTERVAL_SECONDS = 10
"""Matched to the server's collection cadence; a new point cannot arrive faster."""

MIN_SPARK_WIDTH = 10
MAX_SPARK_WIDTH = 80

RETENTION = timedelta(hours=1)
"""What the server keeps for a running job, and so the widest window there can be."""

AXIS_RULE = "┄"
NOW = "now"

LIVE_THRESHOLD = timedelta(seconds=3 * WATCH_INTERVAL_SECONDS)
_FIXED_COLUMNS = 30
"""Everything but the sparklines and the job label: the `gpu=N` column, both numbers, and
the table's padding. Hand-measured against a `589GB/1480GB`-sized number; a wider one
overflows and Rich ellipsizes the labels rather than shrinking the sparklines."""

_SPARKLINE_COLUMNS = 2


def _spark_width(console_width: int, label_width: int = 0) -> int:
    budget = console_width - _FIXED_COLUMNS - label_width
    return max(MIN_SPARK_WIDTH, min(MAX_SPARK_WIDTH, budget // _SPARKLINE_COLUMNS))


def get_metrics_table(
    jobs: Sequence[Job],
    metrics: Sequence[JobMetrics],
    console_width: Optional[int] = None,
) -> RenderableType:
    labels = job_labels(jobs)
    label_width = max((len(label) for label in labels), default=0)
    width = _spark_width(console_width or console.width, label_width)
    window = _shared_window(metrics)

    table = Table(box=None)
    # no headers: the cells read `replica=0` and `gpu=1`, which need no naming
    table.add_column("", no_wrap=True)
    table.add_column("", style="secondary", no_wrap=True)
    table.add_column("UTILIZATION", no_wrap=True)
    table.add_column("MEMORY", no_wrap=True)

    for index, (job, job_metrics) in enumerate(zip(jobs, metrics)):
        if index:
            table.add_row("", "", "", "")
        _add_job(table, job, job_metrics, width, labels[index], window)

    if window is not None:
        table.add_row("", "", "", "")
        # the axis spans the widest chart drawn: a job with fewer samples than cells draws
        # one cell per sample and cannot fill its share
        axis = _time_axis(max(_cells_drawn(m, window, width) for m in metrics), *window)
        table.add_row("", "", axis, axis)
    return table


def job_labels(jobs: Sequence[Job]) -> List[str]:
    groups = {job.job_spec.replica_group for job in jobs}
    show_group = len(groups) > 1
    show_replica = len({job.job_spec.replica_num for job in jobs}) > 1

    labels, last_group = [], None
    for job in jobs:
        parts = []
        if show_group:
            # as `ps`: name the group where it changes, and indent the replicas under it
            group = job.job_spec.replica_group
            parts.append(f"group={group}" if group != last_group else " " * len(f"group={group}"))
            last_group = group
        if show_replica:
            parts.append(f"replica={job.job_spec.replica_num}")
        parts.append(f"job={job.job_spec.job_num}")
        labels.append(" ".join(parts))
    return labels


def _add_job(
    table: Table,
    job: Job,
    metrics: JobMetrics,
    width: int,
    label: str,
    window: Optional[tuple[datetime, datetime]],
) -> None:
    resources = _get_resources(job)
    blanks = _blank_cells(metrics, window, width)
    cells = width - blanks
    table.add_row(
        label,
        "cpu",
        _pad(_cpu_cell(metrics, resources, cells), blanks),
        _pad(_memory_cell(metrics, resources, cells), blanks),
    )
    for index in range(_gpus_num(metrics, resources)):
        table.add_row(
            "",
            f"gpu={index}",
            _pad(_gpu_util_cell(metrics, index, cells), blanks),
            _pad(_gpu_memory_cell(metrics, resources, index, cells), blanks),
        )


def _shared_window(metrics: Sequence[JobMetrics]) -> Optional[tuple[datetime, datetime]]:
    windows = [w for w in (_job_window(m) for m in metrics) if w is not None]
    if not windows:
        return None
    latest, earliest = max(w[1] for w in windows), min(w[0] for w in windows)
    return min(earliest, latest - RETENTION), latest


def _blank_cells(
    metrics: JobMetrics, window: Optional[tuple[datetime, datetime]], width: int
) -> int:
    job_window = _job_window(metrics)
    if job_window is None or window is None:
        return 0
    total = (window[1] - window[0]).total_seconds()
    if total <= 0:
        return 0
    started = (job_window[0] - window[0]).total_seconds()
    return min(width - 1, max(0, round(started / total * width)))


def _cells_drawn(
    metrics: JobMetrics, window: Optional[tuple[datetime, datetime]], width: int
) -> int:
    blanks = _blank_cells(metrics, window, width)
    return blanks + min(width - blanks, _samples_num(metrics))


def _pad(cell: Text, blanks: int) -> Text:
    return cell if blanks <= 0 else Text.assemble(Text(" " * blanks), cell)


def _cpu_cell(job_metrics: JobMetrics, resources: Optional[Resources], width: int) -> Text:
    values = _metric_values(job_metrics, "cpu_usage_percent")
    if not values:
        return no_data()
    cpus = resources.cpus if resources else None
    if cpus:
        values = [v / cpus for v in values]
    # no core count: the value is already normalised to it, and unlike memory there is no
    # total to give the number meaning
    return _chart_cell(sparkline(values, width, HOST_RAMP), f"{values[-1]:.0f}%")


def _memory_cell(job_metrics: JobMetrics, resources: Optional[Resources], width: int) -> Text:
    values = _metric_values(job_metrics, "memory_working_set_bytes")
    if not values:
        return no_data()
    total = resources.memory_mib * 1024 * 1024 if resources else None
    return _capacity_cell(values, total, width, HOST_RAMP)


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
    return _capacity_cell(values, total, width, GPU_RAMP)


def _gpu_util_cell(job_metrics: JobMetrics, index: int, width: int) -> Text:
    values = _metric_values(job_metrics, f"gpu_util_percent_gpu{index}")
    if not values:
        return no_data()
    return _chart_cell(sparkline(values, width, GPU_RAMP), f"{values[-1]:.0f}%")


def _capacity_cell(values: List[float], total: Optional[float], width: int, ramp: Ramp) -> Text:
    percents = [v / total * 100 for v in values] if total else values
    label = format_memory(values[-1], 0)
    if total:
        label += f"/{format_memory(total, 0)}"
    return _chart_cell(sparkline(percents, width, ramp), label)


def _chart_cell(spark: Text, label: str) -> Text:
    return Text.assemble(spark, " ", label)


def _time_axis(width: int, first: datetime, last: datetime) -> Text:
    left, right = _time_label(first), _time_label(last)
    if len(left) + len(right) + 3 > width:
        left, right = _time_label(first, clock_only=True), _time_label(last, clock_only=True)
    if len(left) + len(right) + 2 > width:
        return Text("")
    fill = width - len(left) - len(right) - 2
    axis = Text(f"{left} " + AXIS_RULE * fill + " ", style="grey42")
    axis.append(right, style="bold grey58" if right == NOW else "grey42")
    return axis


def _time_label(moment: datetime, clock_only: bool = False) -> str:
    if datetime.now(timezone.utc) - moment < LIVE_THRESHOLD:
        return NOW
    local = moment.astimezone()
    return f"{local:%H:%M}" if clock_only else f"{local.day} {local:%b %H:%M}"


def _job_window(job_metrics: JobMetrics) -> Optional[tuple[datetime, datetime]]:
    stamps = [t for metric in job_metrics.metrics for t in metric.timestamps]
    return (min(stamps), max(stamps)) if stamps else None


def _samples_num(job_metrics: JobMetrics) -> int:
    return max((len(metric.timestamps) for metric in job_metrics.metrics), default=0)


def _metric_values(job_metrics: JobMetrics, name: str) -> List[Any]:
    """Values for `name`, oldest first. The server sends latest-first; reversing here, once,
    is what keeps every sparkline downstream running left-to-right in time."""
    for metric in job_metrics.metrics:
        if metric.name == name:
            return list(reversed(metric.values))
    return []


def _latest_value(job_metrics: JobMetrics, name: str) -> Optional[Any]:
    values = _metric_values(job_metrics, name)
    return values[-1] if values else None


def _gpus_num(job_metrics: JobMetrics, resources: Optional[Resources]) -> int:
    if resources is not None and resources.gpus:
        return len(resources.gpus)
    detected = _latest_value(job_metrics, "gpus_detected_num")
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
