import json
from datetime import timedelta
from io import StringIO

import pytest
from rich.table import Table

from dstack._internal.cli.services.presets import output as output_module
from dstack._internal.cli.services.presets.output import _add_session, _format_number
from tests._internal.cli.common import plain_console
from tests._internal.cli.preset_factories import get_preset

pytestmark = pytest.mark.windows


class TestFormatNumber:
    def test_large_values_avoid_scientific_notation(self):
        assert _format_number(1723.4) == "1723"
        assert _format_number(999.6) == "1000"

    def test_small_values_keep_three_significant_digits(self):
        assert _format_number(384.8) == "385"
        assert _format_number(15.92) == "15.9"
        assert _format_number(0.99) == "0.99"


class TestFormatPresetBenchmark:
    def test_formats_second_scale_ttft_without_scientific_notation(self):
        preset = get_preset()
        ttft = preset.validations[0].benchmark.metrics.ttft_ms
        ttft.mean = 8148.3
        ttft.p50 = 8151.4
        ttft.p99 = 8334.2

        output = output_module.format_preset_benchmark(preset, verbose=True)

        # Per-user speed is 1/TPOT (p50 7.4ms), not the aggregate over concurrency.
        assert output.startswith("tok/s/user=135 ")
        assert output_module.format_preset_objective(preset).startswith("[secondary]io=1K/128 ")
        assert "ctx=32K" in output
        assert "ttft=8.15s" in output
        assert "e+03" not in output


class TestFormatPresetObjective:
    def test_shows_the_shared_prefix_the_benchmark_actually_used(self):
        preset = get_preset()
        preset.validations[0].benchmark.workload.shared_prefix_tokens = 768

        assert output_module.format_preset_objective(preset) == (
            "[secondary]io=1K/128 prefix=75% conc=1[/]"
        )

    def test_a_preset_saved_before_the_field_existed_still_loads(self):
        # `shared_prefix_tokens` is absent from every preset saved so far.
        preset = get_preset()

        assert preset.validations[0].benchmark.workload.shared_prefix_tokens == 0
        assert output_module.format_preset_objective(preset) == (
            "[secondary]io=1K/128 prefix=0% conc=1[/]"
        )


class TestPrintPresets:
    def test_preserves_benchmark_concurrency_at_narrow_width(self, monkeypatch):
        output = StringIO()
        monkeypatch.setattr(output_module, "console", plain_console(output, width=79))

        output_module.print_presets([get_preset()])

        assert "conc=1" in "".join(output.getvalue().split())

    def test_prints_submitted_column(self, monkeypatch):
        output = StringIO()
        monkeypatch.setattr(output_module, "console", plain_console(output, width=160))
        monkeypatch.setattr(output_module, "pretty_date", lambda _: "2 months ago")

        output_module.print_presets([get_preset()])

        assert "SUBMITTED" in output.getvalue()
        assert "2 months ago" in output.getvalue()


def _session_row(session: dict) -> dict:
    table = Table(box=None)
    for column in ("BASE", "ID", "GPU", "CONSTRAINTS", "BENCHMARK", "", "STATUS", "SUBMITTED"):
        table.add_column(column)
    _add_session(table, session)
    return {
        column.header: "".join(str(cell) for cell in column._cells) for column in table.columns
    }


class TestSessionRow:
    def test_shows_progress_after_status_and_best_benchmark(self):
        row = _session_row(
            {
                "id": "c7e18d52",
                "status": "running",
                "trials_num": 3,
                "trials": {
                    "count": 2,
                    "best": {
                        "tok_s": 2339.0,
                        "tpot_ms": 3.42,
                        "concurrency": 8,
                        "gpu": "A40:48GB:1",
                    },
                },
            }
        )

        assert row["STATUS"] == "[bold sea_green3]trialing[/] [secondary](2/3)[/]"
        # Per-user speed is 1/TPOT, the same definition the preset row uses — not
        # the aggregate over concurrency, which would read 292 here.
        assert row["BENCHMARK"].startswith("tok/s/user=292")
        assert row["GPU"] == "A40:48GB:1"

    def test_shows_the_shared_prefix_when_the_workload_has_one(self):
        row = _session_row(
            {
                "id": "c7e18d52",
                "status": "running",
                "constraints": {
                    "input_tokens": 8192,
                    "output_tokens": 1024,
                    "concurrency": 162,
                    "shared_prefix_tokens": 7373,
                },
            }
        )

        assert row["CONSTRAINTS"] == ("[secondary]io=8K/1K prefix=90% conc=162[/]")

    def test_shows_the_shared_prefix_even_when_requests_are_fully_unique(self):
        # `prefix=0%` is not noise: it decides how much of each request the engine
        # can serve from cache, so a row without it cannot be compared to one with.
        row = _session_row(
            {
                "id": "c7e18d52",
                "status": "running",
                "constraints": {
                    "input_tokens": 8192,
                    "output_tokens": 1024,
                    "concurrency": 162,
                    "shared_prefix_tokens": 0,
                },
            }
        )

        assert "prefix=0%" in row["CONSTRAINTS"]

    def test_shows_zero_progress_without_benchmark(self):
        row = _session_row(
            {"id": "ab12cd34", "status": "running", "trials_num": 3, "trials": {"count": 0}}
        )

        assert row["STATUS"] == "[bold sea_green3]trialing[/] [secondary](0/3)[/]"

    def test_omits_progress_without_trials_data(self):
        row = _session_row({"id": "ab12cd34", "status": "interrupted"})

        assert row["STATUS"] == "[secondary]interrupted[/]"

    def test_counts_without_trials_num(self):
        row = _session_row({"id": "ab12cd34", "status": "interrupted", "trials": {"count": 2}})

        assert row["STATUS"] == "[secondary]interrupted[/] [secondary](2)[/]"


class TestOrdering:
    def test_sorts_all_rows_newest_first_without_grouping(self, monkeypatch):
        buffer = StringIO()
        monkeypatch.setattr(output_module, "console", plain_console(buffer, width=200))
        old = get_preset()
        new = old.model_copy(
            update={"id": "11aa22bb", "created_at": old.created_at + timedelta(days=2)}
        )
        sessions = [
            {
                "id": "aaaaaaaa",
                "status": "interrupted",
                "model": old.base,
                "created_at": "2026-07-01T00:00:00Z",
            },
            {
                "id": "bbbbbbbb",
                "status": "interrupted",
                "model": old.base,
                "created_at": "2026-07-02T00:00:00Z",
            },
        ]

        output_module.print_presets([old, new], sessions=sessions)

        text = buffer.getvalue()
        # Same contract as `dstack ps`: nothing is active here, so exactly one
        # row is shown, the most recent.
        assert "bbbbbbbb" in text
        assert "aaaaaaaa" not in text
        assert "11aa22bb" not in text and old.id not in text

        buffer.truncate(0)
        buffer.seek(0)
        output_module.print_presets([old, new], sessions=sessions, all_presets=True)
        text = buffer.getvalue()

        # With -a: one flat list, newest first, presets and sessions interleaved.
        assert text.index("bbbbbbbb") < text.index("aaaaaaaa") < text.index("11aa22bb")
        assert text.index("11aa22bb") < text.index(old.id)


class TestDoneProgress:
    def test_completed_creation_decorates_preset_row_without_extra_session_row(self, monkeypatch):
        buffer = StringIO()
        monkeypatch.setattr(output_module, "console", plain_console(buffer, width=200))
        preset = get_preset()
        sessions = [
            {
                "id": preset.id,
                "status": "success",
                "model": preset.base,
                "trials_num": 4,
                "trials": {"count": 3},
            }
        ]

        output_module.print_presets([preset], sessions=sessions)

        text = buffer.getvalue()
        assert "(3/4)" in text
        assert "verified" in text
        assert text.count(preset.id) == 1


class TestVerifyingStatus:
    def test_running_session_with_a_verification_record_shows_verifying(self):
        row = _session_row(
            {
                "id": "ab12cd34",
                "status": "running",
                "trials_num": 10,
                "trials": {"count": 6},
                "verification": {"trial": 3, "run_name": "p-2", "status": "verifying"},
            }
        )

        # The trial budget is not spent, which the old inference required.
        assert row["STATUS"] == "[bold deep_sky_blue1]verifying[/] [secondary](6/10)[/]"

    def test_a_failed_attempt_still_counts_as_verifying(self):
        row = _session_row(
            {
                "id": "ab12cd34",
                "status": "running",
                "trials_num": 2,
                "trials": {"count": 2},
                "verification": {"trial": 3, "status": "failed", "reason": "probe never passed"},
            }
        )

        assert row["STATUS"].startswith("[bold deep_sky_blue1]verifying[/]")

    def test_a_spent_trial_budget_alone_stays_trialing(self):
        row = _session_row(
            {"id": "ab12cd34", "status": "running", "trials_num": 2, "trials": {"count": 2}}
        )

        assert row["STATUS"].startswith("[bold sea_green3]trialing[/]")


class TestFailedTrials:
    def test_a_failed_trial_keeps_its_benchmark_but_never_becomes_best(self, tmp_path):
        from dstack._internal.cli.services.presets.session import _summarize_session_trials

        # The failed trial is the fastest. It broke `max_ttft`, so promoting it
        # would put a non-compliant configuration at the top of the listing.
        path = tmp_path / "trials.jsonl"
        path.write_text(
            "\n".join(
                json.dumps(
                    {
                        "benchmark": {
                            "metrics": {"total_output_tokens": tokens, "duration_seconds": 1.0},
                            "workload": {"concurrency": 8},
                        },
                        **({"failed": True} if failed else {}),
                    }
                )
                for tokens, failed in ((100.0, False), (900.0, True), (300.0, False))
            )
        )

        summary = _summarize_session_trials(path)

        assert summary["count"] == 3
        # Still charted: the trial happened and its number is real.
        assert summary["series"] == [100.0, 900.0, 300.0]
        assert summary["best"]["tok_s"] == 300.0
        assert summary["best_failed"]["tok_s"] == 900.0

    def test_reports_the_gpu_when_no_trial_produced_a_benchmark(self, tmp_path):
        from dstack._internal.cli.services.presets.session import _summarize_session_trials

        # Neither `best` nor `best_failed` can carry the hardware here, so this is
        # the only thing left that knows what the run was on.
        path = tmp_path / "trials.jsonl"
        path.write_text(
            json.dumps({"resources": {"gpu": {"name": "MI300X", "memory": "192GB", "count": 1}}})
        )

        summary = _summarize_session_trials(path)

        assert summary["best"] is None
        assert summary["best_failed"] is None
        assert summary["gpu"] == "MI300X:192GB:1"

    def test_the_fastest_failed_trial_is_kept_when_nothing_passed(self, tmp_path):
        from dstack._internal.cli.services.presets.session import _summarize_session_trials

        path = tmp_path / "trials.jsonl"
        path.write_text(
            "\n".join(
                json.dumps(
                    {
                        "benchmark": {
                            "metrics": {
                                "total_output_tokens": tokens,
                                "duration_seconds": 1.0,
                                "tpot_ms": {"p50": 34.4},
                                "ttft_ms": {"p50": 4300.0},
                            },
                            "workload": {"concurrency": 4},
                        },
                        "failed": True,
                    }
                )
                for tokens in (100.0, 300.0, 200.0)
            )
        )

        summary = _summarize_session_trials(path)

        assert summary["best"] is None
        assert summary["best_failed"]["tok_s"] == 300.0

    def test_a_run_that_met_nothing_still_shows_what_it_measured(self):
        row = _session_row(
            {
                "id": "ab12cd34",
                "status": "running",
                "constraints": {"input_tokens": 10000, "output_tokens": 1500},
                "trials": {
                    "count": 1,
                    "series": [100.0],
                    "failed": [True],
                    "best": None,
                    "best_failed": {
                        "tok_s": 100.0,
                        "tpot_ms": 34.4,
                        "ttft_ms": 4300.0,
                        "context_length": 1048576,
                        "concurrency": 4,
                        "gpu": "MI300X:192GB:1",
                    },
                },
            }
        )

        assert "ttft=4.3s" in row["BENCHMARK"]
        assert row["GPU"] == "MI300X:192GB:1"
        # Marked, not just dimmed, so it does not read as a met constraint where
        # styling is absent or invisible to the reader.
        assert "*tok/s/user" in row["BENCHMARK"]


class TestFailedTrialSpark:
    def test_a_trial_that_broke_a_constraint_is_yellow_but_still_charted(self):
        # Its number is real, so it earns a bar; the breach makes it yellow, not
        # red — red is reserved for a trial that produced nothing.
        session = {
            "id": "ab12cd34",
            "status": "running",
            "trials": {
                "count": 3,
                "series": [100.0, 900.0, 300.0],
                "failed": [False, True, False],
            },
        }

        spark = output_module._format_trial_spark(session)

        assert spark.count("gold1") == 1
        assert "indian_red1" not in spark
        assert "·" not in spark
        # The failed trial is the highest number and must not be styled as best.
        assert "sea_green3" not in spark
