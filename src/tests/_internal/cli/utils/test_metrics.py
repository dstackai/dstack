from datetime import datetime, timedelta, timezone
from typing import List
from unittest.mock import MagicMock

import pytest
from rich.console import Console
from rich.theme import Theme

from dstack._internal.cli.utils.metrics import (
    MAX_SPARK_WIDTH,
    MIN_SPARK_WIDTH,
    _axis,
    _metric_values,
    _spark_width,
    format_memory,
    get_metrics_table,
)
from dstack._internal.cli.utils.sparkline import SPARKS
from dstack._internal.core.models.metrics import JobMetrics, Metric

GIB = 1024**3


def _metric(name: str, values: List[float]) -> Metric:
    """Values as the server returns them: latest first."""
    now = datetime.now(timezone.utc)
    return Metric(name=name, timestamps=[now] * len(values), values=list(reversed(values)))


def _job_metrics(
    gpus: int = 0,
    cpus: int = 8,
    cpu_pct: float = 50.0,
    gpu_util: float = 80.0,
    samples: int = 60,
) -> JobMetrics:
    metrics = [
        _metric("cpu_usage_percent", [cpu_pct * cpus] * samples),
        _metric("memory_working_set_bytes", [4 * GIB] * samples),
    ]
    for index in range(gpus):
        metrics.append(_metric(f"gpu_util_percent_gpu{index}", [gpu_util] * samples))
        metrics.append(_metric(f"gpu_memory_usage_bytes_gpu{index}", [60 * GIB] * samples))
    return JobMetrics(metrics=metrics)


def _job(gpus: int = 0, cpus: int = 8, with_resources: bool = True):
    job = MagicMock()
    submission = MagicMock()
    if with_resources:
        resources = MagicMock()
        resources.cpus, resources.memory_mib = cpus, 32 * 1024
        resources.gpus = [MagicMock(memory_mib=80 * 1024) for _ in range(gpus)]
        submission.job_runtime_data.offer.instance.resources = resources
    else:
        submission.job_runtime_data = None
        submission.job_provisioning_data = None
    job.job_submissions = [submission]
    return job


def _render(job, metrics: JobMetrics, width: int = 200) -> str:
    console = Console(width=width, theme=Theme({"secondary": "grey58"}), no_color=True)
    with console.capture() as capture:
        console.print(get_metrics_table(job, metrics, console_width=width))
    return capture.get()


def _lines(output: str) -> List[str]:
    return [line.rstrip() for line in output.splitlines() if line.strip()]


def _row(output: str, label: str) -> str:
    return next(line for line in _lines(output) if line.strip().startswith(label))


class TestMetricValues:
    def test_reverses_server_order_to_oldest_first(self):
        """The service returns points latest to earliest; everything downstream assumes
        the opposite, so this is the one place the series is flipped."""
        job_metrics = JobMetrics(
            metrics=[
                Metric(
                    name="gpu_util_percent_gpu0",
                    timestamps=[datetime.now(timezone.utc)] * 3,
                    values=[30, 20, 10],
                )
            ]
        )
        assert _metric_values(job_metrics, "gpu_util_percent_gpu0") == [10, 20, 30]

    def test_missing_metric_is_empty(self):
        assert _metric_values(JobMetrics(metrics=[]), "cpu_usage_percent") == []


class TestLayout:
    def test_each_row_carries_both_of_its_numbers(self):
        output = _render(_job(gpus=1), _job_metrics(gpus=1, cpu_pct=25.0, gpu_util=77.0))
        assert "25% of 8" in _row(output, "cpu")
        assert "77%" in _row(output, "gpu=0")
        assert "60GB/80GB" in _row(output, "gpu=0")


class TestTimeAxis:
    def test_ends_at_now_while_the_job_is_running(self):
        """Collection is every ~10s, so a running job's newest sample is always `now` --
        and a finished run's is not, which stops a stale table reading as live."""
        assert _lines(_render(_job(gpus=1), _job_metrics(gpus=1)))[-1].endswith("now")

    def test_older_samples_get_an_absolute_local_time(self):
        now = datetime.now(timezone.utc)
        assert _axis(40, now - timedelta(hours=2), now).plain.endswith("now")
        stopped = _axis(40, now - timedelta(hours=2), now - timedelta(hours=1)).plain
        assert "now" not in stopped
        assert ":" in stopped  # a real clock time, not an age

    def test_axis_aligns_with_the_sparklines(self):
        output = _render(_job(gpus=1), _job_metrics(gpus=1))
        axis, cpu_row = _lines(output)[-1], _row(output, "cpu")
        assert axis.index(axis.strip()[0]) == min(cpu_row.index(g) for g in SPARKS if g in cpu_row)

    def test_no_axis_when_there_are_no_samples(self):
        assert "─" not in _render(_job(gpus=1), JobMetrics(metrics=[]))


class TestNoData:
    def test_devices_are_listed_even_with_no_samples(self):
        """The device list comes from the offer, so the shape of the run is known even
        when none of its numbers are."""
        output = _render(_job(gpus=4), JobMetrics(metrics=[]))
        assert sum(1 for ln in _lines(output) if "gpu=" in ln) == 4
        assert "no data" in output

    def test_measured_zero_is_distinguishable_from_missing(self):
        zeros = _render(_job(gpus=1), _job_metrics(gpus=1, gpu_util=0.0, cpu_pct=0.0))
        assert "0%" in zeros
        assert zeros != _render(_job(gpus=1), JobMetrics(metrics=[]))

    def test_no_resources_and_no_metrics_renders_no_device_rows(self):
        assert "gpu=" not in _render(_job(with_resources=False), JobMetrics(metrics=[]))


class TestSparkWidth:
    def test_clamped_at_both_ends(self):
        assert _spark_width(20) == MIN_SPARK_WIDTH
        assert _spark_width(10_000) == MAX_SPARK_WIDTH

    def test_table_fits_the_terminal(self):
        for width in (80, 100, 140, 190, 240):
            output = _render(_job(gpus=8), _job_metrics(gpus=8), width=width)
            assert max(len(ln.rstrip()) for ln in output.splitlines()) <= width


@pytest.mark.parametrize(
    "bytes_value,decimal_places,expected",
    [
        # Test MB values with different decimal places
        (512 * 1024 * 1024, 0, "512MB"),  # exact MB, no decimals
        (512 * 1024 * 1024, 2, "512MB"),  # exact MB, with decimals
        (512.5 * 1024 * 1024, 0, "512MB"),  # decimal MB, no decimals
        (512.5 * 1024 * 1024, 2, "512.5MB"),  # decimal MB, 2 decimals
        (512.5 * 1024 * 1024, 3, "512.5MB"),  # decimal MB, 3 decimals
        (999 * 1024 * 1024, 0, "999MB"),  # just under 1GB, no decimals
        (999 * 1024 * 1024, 2, "999MB"),  # just under 1GB, with decimals
        # Test GB values with different decimal places
        (1.5 * 1024 * 1024 * 1024, 0, "2GB"),  # decimal GB, no decimals
        (1.5 * 1024 * 1024 * 1024, 2, "1.5GB"),  # decimal GB, 2 decimals
        (1.5 * 1024 * 1024 * 1024, 3, "1.5GB"),  # decimal GB, 3 decimals
        (2 * 1024 * 1024 * 1024, 0, "2GB"),  # exact GB, no decimals
        (2 * 1024 * 1024 * 1024, 2, "2GB"),  # exact GB, with decimals
        # Test edge cases
        (0, 0, "0MB"),  # zero bytes, no decimals
        (0, 2, "0MB"),  # zero bytes, with decimals
        (1023 * 1024, 0, "1MB"),  # just under 1MB, no decimals
        (1023 * 1024, 2, "1MB"),  # just under 1MB, with decimals
        (1024 * 1024 * 1024 - 1, 0, "1024MB"),  # just under 1GB, no decimals
        (1024 * 1024 * 1024 - 1, 2, "1024MB"),  # just under 1GB, with decimals
    ],
)
def test_format_memory(bytes_value: int, decimal_places: int, expected: str):
    result = format_memory(bytes_value, decimal_places)
    assert result == expected
