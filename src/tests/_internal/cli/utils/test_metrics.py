import re
from datetime import datetime, timedelta, timezone
from typing import List, Tuple
from unittest.mock import MagicMock

import pytest
from rich.console import Console
from rich.theme import Theme

from dstack._internal.cli.utils.metrics import format_memory, get_metrics_table
from dstack._internal.cli.utils.sparkline import SPARKS
from dstack._internal.core.models.metrics import JobMetrics, Metric

GIB = 1024**3
CAPACITY_GB = 80

# utilization percent, and memory as a fraction of capacity, over `t` in 0..1 oldest to newest
SHAPES = {
    "idle": (lambda t: 1.0, lambda t: 0.05),
    "spike": (lambda t: 100.0 if 0.49 < t < 0.51 else 2.0, lambda t: 0.5),
    "ramp": (lambda t: t * 100.0, lambda t: t * 0.5),
    "saturated": (lambda t: 95.0, lambda t: 0.95),
    "low": (lambda t: 19.0, lambda t: 0.19),
}


def make_run(
    shape: str = "saturated",
    samples: int = 360,
    state: str = "running",
    gpus: int = 1,
    cpus: int = 8,
) -> Tuple[MagicMock, JobMetrics]:
    """A job and its metrics. `state` decides whether the newest sample reads as `now`."""
    newest = datetime.now(timezone.utc)
    if state == "terminated":
        newest -= timedelta(hours=2)
    timestamps = [newest - timedelta(seconds=10 * i) for i in range(samples)]

    def series(fn) -> List[float]:
        oldest_first = [fn(i / max(1, samples - 1)) for i in range(samples)]
        return list(reversed(oldest_first))  # the server returns points newest first

    util, memory = SHAPES[shape]
    metrics = [
        Metric(
            name="cpu_usage_percent",
            timestamps=timestamps,
            values=series(lambda t: util(t) * cpus),
        ),
        Metric(
            name="memory_working_set_bytes",
            timestamps=timestamps,
            values=series(lambda t: memory(t) * 32 * GIB),
        ),
    ]
    for index in range(gpus):
        metrics.append(
            Metric(name=f"gpu_util_percent_gpu{index}", timestamps=timestamps, values=series(util))
        )
        metrics.append(
            Metric(
                name=f"gpu_memory_usage_bytes_gpu{index}",
                timestamps=timestamps,
                values=series(lambda t: memory(t) * CAPACITY_GB * GIB),
            )
        )

    job = MagicMock()
    submission = MagicMock()
    resources = MagicMock()
    resources.cpus, resources.memory_mib = cpus, 32 * 1024
    resources.gpus = [MagicMock(memory_mib=CAPACITY_GB * 1024) for _ in range(gpus)]
    submission.job_runtime_data.offer.instance.resources = resources
    job.job_submissions = [submission]
    return job, JobMetrics(metrics=metrics)


def render(job, metrics: JobMetrics, width: int = 200, color: bool = False) -> str:
    console = Console(
        width=width,
        theme=Theme({"secondary": "grey58"}),
        no_color=not color,
        force_terminal=color,
        color_system="truecolor" if color else None,
    )
    with console.capture() as capture:
        console.print(get_metrics_table(job, metrics, console_width=width))
    return capture.get()


def lines(output: str) -> List[str]:
    return [line.rstrip() for line in output.splitlines() if line.strip()]


def row(output: str, label: str) -> str:
    return next(line for line in lines(output) if line.strip().startswith(label))


def bars(line: str) -> List[int]:
    """Glyph heights of the first sparkline in `line`, left to right."""
    return [SPARKS.index(glyph) for glyph in re.findall(rf"[{SPARKS}]+", line)[0]]


def colours(output: str, label: str) -> set:
    """Distinct colours among the glyphs of `label`'s row."""
    line = next(ln for ln in output.splitlines() if label in ln)
    return {code for code, _ in re.findall(rf"\x1b\[([0-9;]+)m([{SPARKS}])", line)}


class TestRendering:
    def test_idle_draws_flat_and_low_in_one_colour(self):
        """An idle GPU is a flat low line in a single colour, not a rainbow of bands."""
        job, metrics = make_run("idle")
        assert set(bars(row(render(job, metrics), "gpu=0"))) == {0}
        assert len(colours(render(job, metrics, color=True), "gpu=0")) == 1

    def test_a_spike_survives_bucketing(self):
        """One sample at 100% among 360 still draws tall; averaging would erase it."""
        job, metrics = make_run("spike")
        assert max(bars(row(render(job, metrics), "gpu=0"))) == len(SPARKS) - 1

    def test_a_ramp_climbs_left_to_right(self):
        """The server sends points newest first, so a missing reversal mirrors every chart
        and nothing else on screen would give it away."""
        job, metrics = make_run("ramp")
        heights = bars(row(render(job, metrics), "gpu=0"))
        assert heights == sorted(heights)
        assert heights[0] < heights[-1]

    def test_height_is_a_fraction_of_capacity_not_of_the_window(self):
        """19% of capacity looks nearly empty. Rescaling to the window's own maximum would
        draw a steady 154GB of 800GB as a full bar."""
        job, metrics = make_run("low")
        assert max(bars(row(render(job, metrics), "gpu=0"))) <= 1

    def test_the_number_matches_the_last_bar(self):
        """The printed value is the newest sample and the right-hand bar draws that same
        sample, so a value that just dropped cannot show tall beside a 0."""
        job, metrics = make_run("ramp")
        gpu = row(render(job, metrics), "gpu=0")
        assert "100%" in gpu
        assert bars(gpu)[-1] == len(SPARKS) - 1

    def test_no_data_is_not_zero(self):
        """A device we have no metrics for reads differently from an idle one, and its row
        is listed either way -- the device list comes from the offer."""
        job, _ = make_run("idle", gpus=2)
        missing = render(job, JobMetrics(metrics=[]))
        assert "no data" in missing
        assert not re.findall(rf"[{SPARKS}]", missing)
        assert sum(1 for line in lines(missing) if "gpu=" in line) == 2
        assert "1%" in render(*make_run("idle", gpus=2))


class TestWindow:
    @pytest.mark.parametrize("samples", [12, 360], ids=["two-minutes", "an-hour"])
    @pytest.mark.parametrize("state", ["running", "terminated"])
    def test_draws_only_what_was_measured(self, samples: int, state: str):
        """A young run fills part of the row and the timeline stops with it. Drawn to the
        full width it would claim a span nothing was measured over, and Rich would widen
        the column to fit, pulling MEMORY out of line."""
        job, metrics = make_run("ramp", samples=samples, state=state)
        output = render(job, metrics, width=200)
        drawn = len(bars(row(output, "cpu")))
        assert drawn == min(samples, 80)  # 80 is MAX_SPARK_WIDTH
        axis = lines(output)[-1]
        assert [len(segment) for segment in re.split(r"\s{3,}", axis.strip())] == [drawn, drawn]

    @pytest.mark.parametrize("state,live", [("running", True), ("terminated", False)])
    def test_a_finished_run_cannot_look_live(self, state: str, live: bool):
        job, metrics = make_run("saturated", state=state)
        axis = lines(render(job, metrics))[-1]
        assert axis.endswith("now") == live
        if not live:
            assert ":" in axis  # a real clock time, not an age


@pytest.mark.parametrize("width", [80, 100, 140, 190, 240])
def test_fits_every_terminal_width(width: int):
    """Nothing wraps or gets truncated, on the widest realistic row: eight GPUs."""
    job, metrics = make_run("saturated", gpus=8)
    output = render(job, metrics, width=width)
    assert max(len(line.rstrip()) for line in output.splitlines()) <= width
    assert "…" not in output


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
