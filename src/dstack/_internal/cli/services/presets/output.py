from collections import defaultdict
from typing import Any, Callable, Iterable, Optional, Sequence, Union

from rich.table import Table

from dstack._internal.cli.models.preset_agent import PresetTrialResult
from dstack._internal.cli.models.presets import (
    AnyStoredPreset,
    PresetSessionEntry,
    VerifiedPreset,
)
from dstack._internal.cli.utils.common import add_row_from_dict, console
from dstack._internal.core.models.configurations import PresetConfiguration
from dstack._internal.core.models.presets import (
    PresetDatasetConstraints,
    PresetResult,
    PresetWorkload,
)
from dstack._internal.utils.common import pretty_date, pretty_resources

_STATUS_DISPLAY = {
    "verified": ("verified", "secondary"),
    "pulled": ("pulled", "secondary"),
    "running": ("trialing", "bold sea_green3"),
    "verifying": ("verifying", "bold deep_sky_blue1"),
    "interrupted": ("interrupted", "secondary"),
    "failed": ("failed", "indian_red1"),
}


def _format_status(status: str) -> str:
    text, style = _STATUS_DISPLAY.get(status, (status, None))
    return f"[{style}]{text}[/]" if style else text


def _verifying(session: PresetSessionEntry) -> bool:
    return session.verification is not None


_SPARK_BLOCKS = "▁▂▃▄▅▆▇█"


def _format_trial_spark(session: PresetSessionEntry) -> str:
    series = session.trials.series
    failed = session.trials.failed
    if not series:
        return ""
    values = [v for v in series if v is not None]
    if not values:
        return "·" * len(series)
    high = max(values)
    passed = [v for v, f in zip(series, failed) if v is not None and not f]
    best = max(passed) if passed else max(values)
    out = []
    for value, is_failed in zip(series, failed):
        if value is None:
            out.append("[indian_red1]·[/]")
            continue
        glyph = (
            _SPARK_BLOCKS[-1]
            if high <= 0
            else _SPARK_BLOCKS[round(max(value, 0) / high * (len(_SPARK_BLOCKS) - 1))]
        )
        if is_failed:
            style = "gold1" if not passed and value >= best else "indian_red1"
        else:
            style = "bold sea_green3" if value >= best else "secondary"
        out.append(f"[{style}]{glyph}[/]")
    return "".join(out)


def _format_trial_progress(session: PresetSessionEntry, *, in_flight: bool = False) -> str:
    count = session.trials.count
    trials_num = session.state.trials_num
    if not count and trials_num is None:
        return ""
    if in_flight:
        count = min(count + 1, trials_num) if trials_num is not None else count + 1
    progress = str(count)
    if trials_num is not None:
        progress += f"/{trials_num}"
    return f" [secondary]({progress})[/]"


def print_presets(
    presets: Sequence[AnyStoredPreset],
    sessions: Optional[list[PresetSessionEntry]] = None,
    verbose: bool = False,
    all_presets: bool = False,
    limit: Optional[int] = None,
) -> None:
    console.print(
        get_presets_table(
            presets, sessions=sessions, verbose=verbose, all_presets=all_presets, limit=limit
        )
    )
    console.print()


def get_presets_table(
    presets: Sequence[AnyStoredPreset],
    sessions: Optional[list[PresetSessionEntry]] = None,
    verbose: bool = False,
    all_presets: bool = False,
    limit: Optional[int] = None,
) -> Table:
    table = Table(box=None)
    table.add_column("NAME", no_wrap=True)
    table.add_column("ID", no_wrap=True, style="secondary")
    table.add_column("BASE", no_wrap=True, style="secondary")
    if verbose:
        table.add_column("RESOURCES", style="secondary")
    table.add_column("CONSTRAINTS", min_width=len("io=1K/1K"), overflow="fold")
    table.add_column("BENCHMARK", min_width=len("tps=1"), overflow="fold")
    table.add_column("", no_wrap=True)
    table.add_column("STATUS")
    table.add_column("SUBMITTED", style="secondary")
    presets_by_base: dict[str, list[AnyStoredPreset]] = defaultdict(list)
    preset_ids = {preset.id for preset in presets}
    repo_to_base: dict[str, str] = {}
    for preset in presets:
        presets_by_base[preset.base].append(preset)
        repo_to_base[preset.repo] = preset.base
    sessions_by_model: dict[str, list[PresetSessionEntry]] = defaultdict(list)
    creations_by_id: dict[str, PresetSessionEntry] = {}
    for session in sessions or []:
        if session.id in preset_ids:
            # The stored artifact is the completion record. Cleanup can be
            # interrupted before session.json advances to `success`.
            creations_by_id[session.id] = session
            continue
        model = session.state.model
        sessions_by_model[repo_to_base.get(model, model)].append(session)

    # Same contract as `dstack ps`: one flat list, newest first (base is a column,
    # so different models interleave); active-only by default, else the latest row.
    rows: list[tuple[str, Any, bool]] = []
    for preset_list in presets_by_base.values():
        rows += [(preset.created_at.isoformat(), preset, True) for preset in preset_list]
    for session_list in sessions_by_model.values():
        rows += [
            (session.state.created_at.isoformat(), session, False) for session in session_list
        ]
    rows.sort(key=lambda r: r[0], reverse=True)
    only_active = not all_presets and limit is None
    if only_active:
        active = [r for r in rows if not r[2] and r[1].status == "running"]
        rows = active or rows[:1]

    for _, item, is_preset in rows[:limit] if limit is not None else rows:
        if is_preset:
            _add_preset(table, item, verbose=verbose, creation=creations_by_id.get(item.id))
        else:
            _add_session(table, item, verbose=verbose)
    return table


def _add_session(table: Table, session: PresetSessionEntry, *, verbose: bool = False) -> None:
    status_key = session.status
    if status_key == "running" and _verifying(session):
        status_key = "verifying"
    status = _format_status(status_key) + _format_trial_progress(
        session, in_flight=status_key == "running"
    )
    trials = session.trials
    # Nothing passed: fall back to the fastest attempt that did not.
    breached = trials.best is None
    best = trials.best or trials.best_failed
    constraints = session.constraints
    objective = []
    if isinstance(constraints, PresetDatasetConstraints):
        objective.append(f"data={constraints.dataset}")
    elif constraints is not None:
        objective.append(
            f"io={_format_token_count(constraints.input_tokens)}"
            f"/{_format_token_count(constraints.output_tokens)}"
        )
        share = round(100 * constraints.shared_prefix_tokens / constraints.input_tokens)
        if share:
            objective.append(f"prefix={share}%")
    # The shown trial's sweep when it has one, else what was requested.
    concurrency = _result_concurrencies(best.result) if best is not None else []
    if not concurrency and constraints is not None:
        concurrency = constraints.concurrency
    if concurrency:
        objective.append(f"c={_format_concurrency(concurrency)}")
    if verbose and constraints is not None:
        objective.append(f"ctx>={_format_token_count(constraints.min_context_length)}")
        objective.append(f"ttft<={_format_duration_ms(constraints.max_ttft)}")
    benchmark = ""
    if best is not None:
        if objective:
            benchmark = _format_result_benchmark(best.result, verbose=verbose)
        else:
            benchmarks = [r.benchmark for r in best.result if r.benchmark is not None]
            tps = _format_range([b.effective_output_tok_per_s for b in benchmarks], _format_number)
            benchmark = f"c={_format_concurrency(concurrency)} tps={tps}"
    if benchmark and breached:
        # Marked, not only dimmed: colour alone is not a signal.
        benchmark = f"[secondary]*{benchmark}[/]"
    add_row_from_dict(
        table,
        {
            "ID": session.id,
            "BASE": session.state.model,
            "NAME": session.name or "",
            "GPU": trials.gpu or "",
            "RESOURCES": trials.gpu or "",
            "": _format_trial_spark(session),
            "CONSTRAINTS": f"[secondary]{' '.join(objective)}[/]" if objective else "",
            "BENCHMARK": benchmark,
            "STATUS": status,
            "SUBMITTED": pretty_date(session.state.created_at),
        },
    )


def _add_preset(
    table: Table,
    preset: AnyStoredPreset,
    *,
    verbose: bool,
    creation: Optional[PresetSessionEntry] = None,
) -> None:
    groups = preset.service.replica_groups
    row = {
        "ID": preset.id,
        "NAME": preset.name or "",
        "RESOURCES": _format_resources(groups[0].resources, verbose=verbose),
        "BASE": preset.base,
        "STATUS": _format_status(preset.status)
        + (_format_trial_progress(creation) if creation is not None else ""),
        "": _format_trial_spark(creation) if creation is not None else "",
        "CONSTRAINTS": format_preset_objective(
            preset,
            verbose=verbose,
        ),
        "BENCHMARK": format_preset_benchmark(preset, verbose=verbose),
        "SUBMITTED": pretty_date(preset.created_at),
    }
    if verbose and preset.repo != preset.base:
        row["BASE"] = f"[secondary]  repo={preset.repo}[/]"
    add_row_from_dict(table, row)
    if len(groups) > 1:
        for group in groups:
            add_row_from_dict(
                table,
                {
                    "BASE": f"  group={group.name}",
                    "RESOURCES": _format_resources(group.resources, verbose=verbose),
                },
                style="secondary",
            )


def format_preset_objective(
    preset: AnyStoredPreset,
    *,
    verbose: bool = False,
) -> str:
    workload = _measured_workload_from_preset(preset)
    if isinstance(preset, VerifiedPreset):
        return _format_creation_objective(preset.configuration, workload, verbose=verbose)
    # A pulled preset carries no creation context; the measured workload is its
    # honest record of the conditions the numbers hold for.
    parts = []
    if workload.dataset is not None:
        parts.append(f"data={workload.dataset}")
    else:
        parts.append(
            f"io={_format_token_count(workload.input_tokens)}"
            f"/{_format_token_count(workload.output_tokens)}"
        )
        share = round(100 * workload.shared_prefix_tokens / workload.input_tokens)
        if share:
            parts.append(f"prefix={share}%")
    parts.append(f"c={_format_concurrency([r.concurrency for r in preset.result])}")
    return f"[secondary]{' '.join(parts)}[/]"


def _measured_workload_from_preset(preset: AnyStoredPreset) -> PresetWorkload:
    for r in preset.result:
        if r.benchmark is not None:
            return r.benchmark.workload
    # Unreachable for a stored preset: verification requires at least one
    # completed benchmark. Kept so the function returns on every path.
    raise ValueError(f"preset {preset.id} has no measured workload")


def _format_concurrency(values: list[int]) -> str:
    if len(values) == 1:
        return str(values[0])
    return f"{min(values)}..{max(values)}"


def _format_creation_objective(
    configuration: PresetConfiguration, workload: PresetWorkload, *, verbose: bool
) -> str:
    parts = []
    if configuration.dataset is not None:
        parts.append(f"data={configuration.dataset}")
    else:
        input_tokens = configuration.effective_input_tokens
        parts.append(
            f"io={_format_token_count(input_tokens)}"
            f"/{_format_token_count(configuration.effective_output_tokens)}"
        )
        share = round(100 * (configuration.shared_prefix_tokens or 0) / input_tokens)
        if share:
            parts.append(f"prefix={share}%")
    parts.append(f"c={_format_concurrency(configuration.concurrency or [workload.concurrency])}")
    if verbose and configuration.min_context_length is not None:
        parts.append(f"ctx>={_format_token_count(configuration.min_context_length)}")
    if verbose and configuration.max_ttft is not None:
        parts.append(f"ttft<={_format_duration_ms(configuration.max_ttft)}")
    return f"[secondary]{' '.join(parts)}[/]"


def _passing_result(preset: AnyStoredPreset) -> list[PresetResult]:
    """The measured entries that met the requested constraints."""
    measured = [r for r in preset.result if r.benchmark is not None]
    if not isinstance(preset, VerifiedPreset):
        # A pulled preset carries no requested constraints to breach.
        return measured
    return [r for r in measured if not _breaches_constraints(r, preset.configuration)]


def _breaches_constraints(r: PresetResult, configuration: PresetConfiguration) -> bool:
    assert r.benchmark is not None
    if (
        configuration.max_ttft is not None
        and r.benchmark.metrics.ttft_ms.p50 > configuration.max_ttft
    ):
        return True
    return (
        configuration.min_context_length is not None
        and r.context_length is not None
        and r.context_length < configuration.min_context_length
    )


def format_preset_benchmark(preset: AnyStoredPreset, *, verbose: bool = False) -> str:
    passing = _passing_result(preset)
    if passing:
        return _format_result_benchmark(passing, verbose=verbose)
    text = _format_result_benchmark(preset.result, verbose=verbose)
    return f"[secondary]*{text}[/]"


# Entries of a stored preset and of a session's trial share the fields read here.
AnyResult = Union[PresetResult, PresetTrialResult]


def _format_result_benchmark(result: Sequence[AnyResult], *, verbose: bool) -> str:
    """Each metric as its range over the entries that have a benchmark."""
    benchmarks = [r.benchmark for r in result if r.benchmark is not None]
    context_lengths = [r.context_length for r in result if r.context_length is not None]
    # Lead with per-user tps: comparable across rows regardless of concurrency.
    parts = [
        f"tps/user={_format_range([b.effective_per_user_tok_per_s for b in benchmarks], _format_number)}"
    ]
    if verbose:
        parts.append(
            f"tps={_format_range([b.effective_output_tok_per_s for b in benchmarks], _format_number)}"
        )
    parts.append(
        f"ttft={_format_range([b.metrics.ttft_ms.p50 for b in benchmarks], _format_duration_ms)}"
    )
    if context_lengths:
        parts.append(f"ctx={_format_range(context_lengths, _format_token_count)}")
    return " ".join(parts)


def _result_concurrencies(result: Sequence[AnyResult]) -> list[int]:
    """Old `trial.json` entries carry the concurrency only inside the benchmark."""
    values = []
    for r in result:
        if r.concurrency is not None:
            values.append(r.concurrency)
        elif r.benchmark is not None:
            values.append(r.benchmark.workload.concurrency)
    return values


def _format_range(values: Iterable[float], format_value: Callable[[Any], str]) -> str:
    values = list(values)
    low, high = min(values), max(values)
    if low == high:
        return format_value(low)
    return f"{format_value(low)}..{format_value(high)}"


def _format_duration_ms(value: float) -> str:
    # 999.6 rounds to 1000, which must read as 1s rather than 1000ms.
    if value < 999.5:
        return f"{_format_number(value)}ms"
    return f"{_format_number(value / 1000)}s"


def _format_token_count(value: int) -> str:
    # The conventional name: exact binary multiples keep binary names
    # (32768 is "32K"), anything else rounds as decimal (1500 is "1.5K").
    for divisor, suffix in ((1024 * 1024, "M"), (1024, "K")):
        if value >= divisor and value % divisor == 0:
            return f"{value // divisor}{suffix}"
    if value >= 999_950:
        return f"{value / 1_000_000:.1f}".removesuffix(".0") + "M"
    if value >= 1000:
        return f"{value / 1000:.1f}".removesuffix(".0") + "K"
    return str(value)


def _format_number(value: float) -> str:
    # `g` switches to scientific notation for values >= 1000 (after rounding).
    if abs(value) >= 999.5:
        return f"{value:.0f}"
    return f"{value:.3g}"


def _format_resources(resources, *, verbose: bool) -> str:
    if resources is None:
        return "-"
    if verbose:
        return resources.pretty_format()
    gpu = resources.gpu
    if gpu is None or gpu.count.max == 0:
        return "-"
    formatted = pretty_resources(
        gpu_vendor=gpu.vendor,
        gpu_name=",".join(gpu.name) if gpu.name else None,
        gpu_count=gpu.count,
        gpu_memory=gpu.memory,
        total_gpu_memory=gpu.total_memory,
        compute_capability=gpu.compute_capability,
    )
    return formatted.removeprefix("gpu=") or "-"
