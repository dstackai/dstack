import re
from datetime import datetime, timedelta, timezone
from typing import List, Tuple
from unittest.mock import MagicMock

import pytest
from rich.console import Console
from rich.theme import Theme

from dstack._internal.cli.utils.metrics import (
    _job_window,
    _time_axis,
    _time_label,
    format_memory,
    get_metrics_table,
    job_labels,
)
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
    replica: int = 0,
    job_num: int = 0,
    group: str = "default",
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
    job.job_spec.replica_num, job.job_spec.job_num = replica, job_num
    job.job_spec.replica_group = group
    submission = MagicMock()
    resources = MagicMock()
    resources.cpus, resources.memory_mib = cpus, 32 * 1024
    resources.gpus = [MagicMock(memory_mib=CAPACITY_GB * 1024) for _ in range(gpus)]
    submission.job_runtime_data.offer.instance.resources = resources
    job.job_submissions = [submission]
    return job, JobMetrics(metrics=metrics)


def render(jobs, metrics, width: int = 200, color: bool = False) -> str:
    """`jobs`/`metrics` may be a single pair, as most tests use, or whole lists."""
    if not isinstance(jobs, list):
        jobs, metrics = [jobs], [metrics]
    console = Console(
        width=width,
        theme=Theme({"secondary": "grey58"}),
        no_color=not color,
        force_terminal=color,
        color_system="truecolor" if color else None,
    )
    with console.capture() as capture:
        console.print(get_metrics_table(jobs, metrics, console_width=width))
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
    @pytest.mark.parametrize("state", ["running", "terminated"])
    def test_an_hour_old_run_fills_the_row(self, state: str):
        job, metrics = make_run("ramp", samples=360, state=state)
        assert len(bars(row(render(job, metrics), "job=0"))) == 80  # MAX_SPARK_WIDTH

    def test_a_young_run_fills_only_its_share(self):
        job, metrics = make_run("ramp", samples=12)
        output = render(job, metrics, width=120)
        assert len(bars(row(output, "job=0"))) < 5
        axis = lines(output)[-1]
        assert axis.endswith("now")

    @pytest.mark.parametrize("state,live", [("running", True), ("terminated", False)])
    def test_a_finished_run_cannot_look_live(self, state: str, live: bool):
        job, metrics = make_run("saturated", state=state)
        axis = lines(render(job, metrics))[-1]
        assert axis.endswith("now") == live
        if not live:
            assert ":" in axis  # a real clock time, not an age

    @pytest.mark.parametrize("age_seconds,live", [(13, True), (45, False)])
    def test_a_sample_may_lag_a_few_intervals_and_still_read_as_live(self, age_seconds, live):
        moment = datetime.now(timezone.utc) - timedelta(seconds=age_seconds)
        assert (_time_label(moment) == "now") == live

    @pytest.mark.parametrize("state,emphasised", [("running", True), ("terminated", False)])
    def test_only_a_live_edge_is_emphasised(self, state: str, emphasised: bool):
        job, metrics = make_run("saturated", state=state)
        axis = _time_axis(60, *_job_window(metrics))
        styles = {str(span.style) for span in axis.spans}
        assert ("bold grey58" in styles) == emphasised


class TestJobs:
    def test_every_job_is_shown_and_keyed(self):
        run = [make_run(replica=r, gpus=1) for r in range(3)]
        output = render([j for j, _ in run], [m for _, m in run])
        assert [ln.split()[0] for ln in lines(output) if ln.startswith(" replica")] == [
            "replica=0",
            "replica=1",
            "replica=2",
        ]

    @pytest.mark.parametrize(
        "jobs,expected",
        [
            ([(0, 0, "default")], ["job=0"]),
            ([(r, 0, "default") for r in range(2)], ["replica=0 job=0", "replica=1 job=0"]),
            ([(0, n, "default") for n in range(2)], ["job=0", "job=1"]),
            (
                [(0, 0, "spot"), (1, 0, "spot"), (2, 0, "on-demand")],
                [
                    "group=spot replica=0 job=0",
                    "replica=1 job=0",  # same group: named once, replicas indented under it
                    "group=on-demand replica=2 job=0",
                ],
            ),
        ],
        ids=["one-job", "replicas", "nodes", "groups"],
    )
    def test_labels_name_only_what_distinguishes(self, jobs, expected):
        built = [make_run(replica=r, job_num=j, group=g)[0] for r, j, g in jobs]
        assert [" ".join(label.split()) for label in job_labels(built)] == expected

    def test_a_late_job_starts_where_it_started(self):
        old, young = make_run(samples=360, replica=0), make_run(samples=12, replica=1)
        output = render([old[0], young[0]], [old[1], young[1]])
        first = {
            label: min(row(output, label).index(g) for g in SPARKS if g in row(output, label))
            for label in ("replica=0", "replica=1")
        }
        assert len(bars(row(output, "replica=0"))) > len(bars(row(output, "replica=1")))
        assert first["replica=1"] > first["replica=0"]  # pushed right by the blank


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
