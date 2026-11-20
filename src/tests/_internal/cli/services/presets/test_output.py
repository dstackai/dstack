from datetime import datetime, timedelta, timezone
from io import StringIO

import pytest
from rich.table import Table

from dstack._internal.cli.models.preset_agent import PresetTrial, PresetTrialResult
from dstack._internal.cli.models.presets import PresetSessionEntry, PulledPreset
from dstack._internal.cli.services.presets import output as output_module
from dstack._internal.cli.services.presets.output import _add_session, _format_number
from dstack._internal.core.models.presets import PortablePreset, PresetWorkload
from dstack._internal.utils.common import get_or_error
from tests._internal.cli.common import (
    get_preset,
    get_preset_constraints,
    get_session_entry,
    get_trial_result,
    get_trials_summary,
    plain_console,
)

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
        ttft = get_or_error(preset.result[0].benchmark).metrics.ttft_ms
        ttft.mean = 8148.3
        ttft.p50 = 8151.4
        ttft.p99 = 8334.2

        output = output_module.format_preset_benchmark(preset, verbose=True)

        # Per-user speed is 1/TPOT (p50 7.4ms), not the aggregate over concurrency.
        assert output.startswith("tps/user=133 ")
        assert output_module.format_preset_objective(preset).startswith("[secondary]io=1K/128 ")
        assert "ctx=32K" in output
        assert "ttft=8.15s" in output
        assert "e+03" not in output


class TestFormatPresetObjective:
    def test_shows_the_requested_shared_prefix(self):
        preset = get_preset()
        preset.configuration.shared_prefix_tokens = 768

        assert output_module.format_preset_objective(preset) == (
            "[secondary]io=1K/128 prefix=75% c=1[/]"
        )

    def test_treats_an_unset_shared_prefix_as_none_shared(self):
        preset = get_preset()

        assert preset.configuration.shared_prefix_tokens is None
        assert output_module.format_preset_objective(preset) == ("[secondary]io=1K/128 c=1[/]")

    def test_shows_the_dataset_instead_of_the_request_shape(self):
        # A dataset defines its own request shape, so the cell names it instead.
        preset = get_preset()
        preset.configuration.dataset = "spec_bench"

        assert output_module.format_preset_objective(preset) == (
            "[secondary]data=spec_bench c=1[/]"
        )

    def test_renders_the_requested_workload_not_the_measured_one(self):
        # They diverge with a dataset, where the benchmark records measured means.
        preset = get_preset()
        preset.configuration.dataset = "spec_bench"
        benchmark = get_or_error(preset.result[0].benchmark)
        benchmark.workload = PresetWorkload(
            api=benchmark.workload.api,
            num_requests=benchmark.workload.num_requests,
            input_tokens=347,
            output_tokens=2451,
            concurrency=8,
            dataset="spec_bench",
        )

        assert output_module.format_preset_objective(preset) == (
            "[secondary]data=spec_bench c=1[/]"
        )


def _get_pulled_preset() -> PulledPreset:
    verified = get_preset()
    return PulledPreset(
        id=verified.id,
        name="main/qwen",
        created_at=datetime(2026, 2, 3, 4, 5, tzinfo=timezone.utc),
        **{field: getattr(verified, field) for field in PortablePreset.model_fields},
    )


class TestRemotePresetRow:
    def test_objective_falls_back_to_the_measured_workload(self):
        # A pulled preset carries no creation context; the benchmark workload is
        # its record of the conditions the numbers hold for.
        assert output_module.format_preset_objective(_get_pulled_preset()) == (
            "[secondary]io=1K/128 c=1[/]"
        )

    def test_renders_a_pulled_preset_row(self, monkeypatch):
        output = StringIO()
        monkeypatch.setattr(output_module, "console", plain_console(output, width=200))

        output_module.print_presets([_get_pulled_preset()])

        text = output.getvalue()
        assert "main/qwen" in text
        assert "io=1K/128" in text
        assert "ctx=32K" in text


class TestPrintPresets:
    def test_preserves_constraints_and_benchmark_at_narrow_width(self, monkeypatch):
        output = StringIO()
        monkeypatch.setattr(output_module, "console", plain_console(output, width=79))

        output_module.print_presets([get_preset()])

        # Both columns wrap rather than clip, so their full content survives even
        # when a long model name would otherwise squeeze them out.
        joined = "".join(output.getvalue().split())
        assert "c=1" in joined
        assert "ttft=108ms" in joined

    def test_prints_submitted_column(self, monkeypatch):
        output = StringIO()
        monkeypatch.setattr(output_module, "console", plain_console(output, width=160))
        monkeypatch.setattr(output_module, "pretty_date", lambda _: "2 months ago")

        output_module.print_presets([get_preset()])

        assert "SUBMITTED" in output.getvalue()
        assert "2 months ago" in output.getvalue()


def _session_row(session: PresetSessionEntry) -> dict:
    table = Table(box=None)
    for column in (
        "BASE",
        "ID",
        "NAME",
        "RESOURCES",
        "CONSTRAINTS",
        "BENCHMARK",
        "",
        "STATUS",
        "SUBMITTED",
    ):
        table.add_column(column)
    _add_session(table, session)
    return {
        column.header: "".join(str(cell) for cell in column._cells) for column in table.columns
    }


class TestSessionRow:
    def test_shows_progress_after_status_and_best_benchmark(self):
        row = _session_row(
            get_session_entry(
                id="c7e18d52",
                trials_num=3,
                trials=get_trials_summary(
                    2,
                    best=PresetTrial(
                        result=[get_trial_result(tok_s=2339.0, tpot_ms=3.42, concurrency=8)]
                    ),
                    gpu="A40:48GB:1",
                ),
            )
        )

        # 2 completed, so the 3rd is the one being trialed.
        assert row["STATUS"] == "[bold sea_green3]trialing[/] [secondary](3/3)[/]"
        # Per-user speed is 1/TPOT, the same definition the preset row uses — not
        # the aggregate over concurrency, which would read 292 here.
        assert row["BENCHMARK"].startswith("tps/user=292")
        assert row["RESOURCES"] == "A40:48GB:1"

    def test_shows_the_shared_prefix_when_the_workload_has_one(self):
        row = _session_row(
            get_session_entry(
                id="c7e18d52",
                constraints=get_preset_constraints(
                    input_tokens=8192,
                    output_tokens=1024,
                    concurrency=[162],
                    shared_prefix_tokens=7373,
                ),
            )
        )

        assert row["CONSTRAINTS"] == ("[secondary]io=8K/1K prefix=90% c=162[/]")

    def test_shows_the_dataset_for_a_session_with_a_custom_dataset(self):
        row = _session_row(
            get_session_entry(
                id="c7e18d52",
                constraints=get_preset_constraints(dataset="spec_bench", concurrency=[4]),
            )
        )

        assert row["CONSTRAINTS"] == ("[secondary]data=spec_bench c=4[/]")

    def test_omits_the_shared_prefix_when_requests_are_fully_unique(self):
        # A zero prefix is the default; only a non-zero share is information.
        # can serve from cache, so a row without it cannot be compared to one with.
        row = _session_row(
            get_session_entry(
                id="c7e18d52",
                constraints=get_preset_constraints(
                    input_tokens=8192,
                    output_tokens=1024,
                    concurrency=[162],
                    shared_prefix_tokens=0,
                ),
            )
        )

        assert "prefix" not in row["CONSTRAINTS"]

    def test_shows_zero_progress_without_benchmark(self):
        row = _session_row(get_session_entry(trials_num=3))

        assert row["STATUS"] == "[bold sea_green3]trialing[/] [secondary](1/3)[/]"

    def test_verifying_keeps_the_completed_count(self):
        row = _session_row(
            get_session_entry(trials_num=3, trials=get_trials_summary(3), verification="verifying")
        )

        assert row["STATUS"] == "[bold deep_sky_blue1]verifying[/] [secondary](3/3)[/]"

    def test_omits_progress_without_trials_data(self):
        row = _session_row(get_session_entry(status="interrupted"))

        assert row["STATUS"] == "[secondary]interrupted[/]"

    def test_counts_without_trials_num(self):
        row = _session_row(get_session_entry(status="interrupted", trials=get_trials_summary(2)))

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
            get_session_entry(
                id="aaaaaaaa",
                status="interrupted",
                model=old.base,
                created_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
            ),
            get_session_entry(
                id="bbbbbbbb",
                status="interrupted",
                model=old.base,
                created_at=datetime(2026, 7, 2, tzinfo=timezone.utc),
            ),
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
    @pytest.mark.parametrize("session_status", ["success", "interrupted", "failed"])
    def test_saved_preset_owns_row_regardless_of_session_status(self, monkeypatch, session_status):
        buffer = StringIO()
        monkeypatch.setattr(output_module, "console", plain_console(buffer, width=200))
        preset = get_preset()
        sessions = [
            get_session_entry(
                id=preset.id,
                status=session_status,
                model=preset.base,
                trials_num=4,
                trials=get_trials_summary(3),
            )
        ]

        output_module.print_presets([preset], sessions=sessions)

        text = buffer.getvalue()
        assert "(3/4)" in text
        assert "verified" in text
        assert text.count(preset.id) == 1


class TestVerifyingStatus:
    def test_running_session_with_a_verification_record_shows_verifying(self):
        row = _session_row(
            get_session_entry(
                trials_num=10, trials=get_trials_summary(6), verification="verifying"
            )
        )

        # The trial budget is not spent, which the old inference required.
        assert row["STATUS"] == "[bold deep_sky_blue1]verifying[/] [secondary](6/10)[/]"

    def test_a_failed_attempt_still_counts_as_verifying(self):
        row = _session_row(
            get_session_entry(trials_num=2, trials=get_trials_summary(2), verification="failed")
        )

        assert row["STATUS"].startswith("[bold deep_sky_blue1]verifying[/]")

    def test_a_spent_trial_budget_alone_stays_trialing(self):
        row = _session_row(get_session_entry(trials_num=2, trials=get_trials_summary(2)))

        assert row["STATUS"].startswith("[bold sea_green3]trialing[/]")


def _write_trials(tmp_path, trials: list[PresetTrial]):
    trials_dir = tmp_path / "trials"
    for number, trial in enumerate(trials, 1):
        (trials_dir / str(number)).mkdir(parents=True)
        (trials_dir / str(number) / "trial.json").write_text(trial.model_dump_json())
    return trials_dir


class TestFailedTrials:
    def test_a_failed_trial_keeps_its_benchmark_but_never_becomes_best(self, tmp_path):
        from dstack._internal.cli.services.presets.session import _summarize_session_trials

        # The failed trial is the fastest. It broke `max_ttft`, so promoting it
        # would put a non-compliant configuration at the top of the listing.
        trials = [
            PresetTrial(result=[get_trial_result(tok_s=tokens, concurrency=8, failed=failed)])
            for tokens, failed in ((100.0, False), (900.0, True), (300.0, False))
        ]
        trials_dir = _write_trials(tmp_path, trials)

        summary = _summarize_session_trials(trials_dir)

        assert summary.count == 3
        # Still charted: the trial happened and its number is real.
        assert summary.series == [100.0, 900.0, 300.0]
        assert summary.best == trials[2]
        assert summary.best_failed == trials[1]

    def test_reports_the_gpu_when_no_trial_produced_a_benchmark(self, tmp_path):
        from dstack._internal.cli.services.presets.session import _summarize_session_trials

        # Neither `best` nor `best_failed` can carry the hardware here, so this is
        # the only thing left that knows what the run was on.
        trials_dir = _write_trials(
            tmp_path,
            [
                PresetTrial(
                    resources={"gpu": {"name": "MI300X", "memory": "192GB", "count": 1}},
                    result=[PresetTrialResult(concurrency=4, failed=True)],
                )
            ],
        )

        summary = _summarize_session_trials(trials_dir)

        assert summary.best is None
        assert summary.best_failed is None
        assert summary.gpu == "MI300X:192GB:1"

    def test_reports_the_gpu_of_a_single_node_group(self, tmp_path):
        from dstack._internal.cli.services.presets.session import _summarize_session_trials

        trials_dir = _write_trials(
            tmp_path,
            [
                PresetTrial(
                    groups=[[{"gpu": {"name": "MI300X", "memory": "192GB", "count": 1}}]],
                    result=[get_trial_result()],
                )
            ],
        )

        summary = _summarize_session_trials(trials_dir)

        assert summary.gpu == "MI300X:192GB:1"

    def test_counts_the_worker_nodes_of_a_disaggregated_trial(self, tmp_path):
        from dstack._internal.cli.services.presets.session import _summarize_session_trials

        # The CPU router has no GPU: it must neither blank the column nor split it.
        h200 = {"gpu": {"name": "H200", "memory": "141GB", "count": 8}}
        trials_dir = _write_trials(
            tmp_path,
            [
                PresetTrial(
                    groups=[[{"cpu": "16"}], [h200], [h200, h200]],
                    result=[get_trial_result()],
                )
            ],
        )

        summary = _summarize_session_trials(trials_dir)

        assert summary.gpu == "H200:141GB:8 x3"

    def test_shows_the_split_when_roles_ran_different_gpus(self, tmp_path):
        from dstack._internal.cli.services.presets.session import _summarize_session_trials

        h100 = {"gpu": {"name": "H100", "memory": "80GB", "count": 8}}
        trials_dir = _write_trials(
            tmp_path,
            [
                PresetTrial(
                    groups=[
                        [{"gpu": {"name": "H200", "memory": "141GB", "count": 8}}],
                        [h100, h100],
                    ],
                    result=[get_trial_result()],
                )
            ],
        )

        summary = _summarize_session_trials(trials_dir)

        # Group order, not sorted: the roles read in the order they ran.
        assert summary.gpu == "H200:141GB:8 + H100:80GB:8 x2"

    def test_the_fastest_failed_trial_is_kept_when_nothing_passed(self, tmp_path):
        from dstack._internal.cli.services.presets.session import _summarize_session_trials

        trials = [
            PresetTrial(
                result=[
                    get_trial_result(
                        tok_s=tokens, tpot_ms=41.7, ttft_ms=4300.0, concurrency=4, failed=True
                    )
                ]
            )
            for tokens in (100.0, 300.0, 200.0)
        ]
        trials_dir = _write_trials(tmp_path, trials)

        summary = _summarize_session_trials(trials_dir)

        assert summary.best is None
        assert summary.best_failed == trials[1]

    def test_a_run_that_met_nothing_still_shows_what_it_measured(self):
        row = _session_row(
            get_session_entry(
                constraints=get_preset_constraints(input_tokens=10000, output_tokens=1500),
                trials=get_trials_summary(
                    1,
                    series=[100.0],
                    failed=[True],
                    best_failed=PresetTrial(
                        result=[
                            get_trial_result(
                                tok_s=100.0,
                                tpot_ms=34.4,
                                ttft_ms=4300.0,
                                concurrency=4,
                                context_length=1048576,
                                failed=True,
                            )
                        ]
                    ),
                    gpu="MI300X:192GB:1",
                ),
            )
        )

        assert "ttft=4.3s" in row["BENCHMARK"]
        assert row["RESOURCES"] == "MI300X:192GB:1"
        # Marked, not just dimmed, so it does not read as a met constraint where
        # styling is absent or invisible to the reader.
        assert "*tps/user" in row["BENCHMARK"]


class TestSweepRow:
    def test_shows_the_passing_sweep_of_the_best_trial_as_ranges(self, tmp_path):
        from dstack._internal.cli.services.presets.session import _summarize_session_trials

        # The trial broke `max_ttft` at 192 only, so the row ranges over 48 and 96.
        trial = PresetTrial(
            result=[
                get_trial_result(
                    tok_s=100, tpot_ms=10.0, ttft_ms=400.0, concurrency=48, context_length=32768
                ),
                get_trial_result(
                    tok_s=180, tpot_ms=20.0, ttft_ms=800.0, concurrency=96, context_length=32768
                ),
                get_trial_result(
                    tok_s=200,
                    tpot_ms=40.0,
                    ttft_ms=6000.0,
                    concurrency=192,
                    context_length=32768,
                    failed=True,
                ),
            ]
        )
        summary = _summarize_session_trials(_write_trials(tmp_path, [trial]))

        row = _session_row(
            get_session_entry(
                trials=summary, constraints=get_preset_constraints(concurrency=[48, 96, 192])
            )
        )

        assert row["CONSTRAINTS"] == "[secondary]io=1K/1K c=48..96[/]"
        assert row["BENCHMARK"] == "tps/user=50..100 ttft=400ms..800ms ctx=32K"

    def test_falls_back_to_the_whole_failed_sweep_when_nothing_passed(self, tmp_path):
        from dstack._internal.cli.services.presets.session import _summarize_session_trials

        trial = PresetTrial(
            result=[
                get_trial_result(
                    tok_s=100,
                    tpot_ms=10.0,
                    ttft_ms=400.0,
                    concurrency=48,
                    context_length=32768,
                    failed=True,
                ),
                get_trial_result(
                    tok_s=180,
                    tpot_ms=20.0,
                    ttft_ms=800.0,
                    concurrency=96,
                    context_length=32768,
                    failed=True,
                ),
                get_trial_result(
                    tok_s=200,
                    tpot_ms=40.0,
                    ttft_ms=6000.0,
                    concurrency=192,
                    context_length=32768,
                    failed=True,
                ),
            ]
        )
        summary = _summarize_session_trials(_write_trials(tmp_path, [trial]))

        row = _session_row(
            get_session_entry(
                trials=summary, constraints=get_preset_constraints(concurrency=[48, 96, 192])
            )
        )

        assert row["CONSTRAINTS"] == "[secondary]io=1K/1K c=48..192[/]"
        assert row["BENCHMARK"] == "[secondary]*tps/user=25..100 ttft=400ms..6s ctx=32K[/]"


class TestFailedTrialSpark:
    def test_a_trial_that_broke_a_constraint_is_charted_but_not_the_best(self):
        # Its number is real, so it earns a bar rather than a `·`, and green goes
        # to the best trial that meets the constraints even on a lower number.
        session = get_session_entry(
            trials=get_trials_summary(3, series=[100.0, 900.0, 300.0], failed=[False, True, False])
        )

        spark = output_module._format_trial_spark(session)

        assert spark.count("indian_red1") == 1
        assert spark.count("sea_green3") == 1
        assert "gold1" not in spark
        assert "·" not in spark

    def test_the_best_failed_trial_is_gold_while_none_passes(self):
        # With nothing meeting the constraints, the best result so far is still
        # what the run has to show; the rest are context.
        session = get_session_entry(
            trials=get_trials_summary(3, series=[100.0, 900.0, 300.0], failed=[True, True, True])
        )

        spark = output_module._format_trial_spark(session)

        assert spark.count("gold1") == 1
        assert spark.count("indian_red1") == 2
        assert "sea_green3" not in spark
