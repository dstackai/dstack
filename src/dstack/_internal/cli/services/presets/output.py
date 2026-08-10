from collections import defaultdict
from datetime import datetime
from typing import Any, Optional

from rich.table import Table

from dstack._internal.cli.models.presets import (
    Preset,
)
from dstack._internal.cli.utils.common import add_row_from_dict, console
from dstack._internal.utils.common import pretty_date, pretty_resources

_STATUS_DISPLAY = {
    "ready": ("verified", "grey"),
    "running": ("trialing", "bold sea_green3"),
    "verifying": ("verifying", "bold deep_sky_blue1"),
    "interrupted": ("interrupted", "secondary"),
    "failed": ("failed", "indian_red1"),
}


def _format_status(status: str) -> str:
    text, style = _STATUS_DISPLAY.get(status, (status, None))
    return f"[{style}]{text}[/]" if style else text


def _verifying(session: dict[str, Any]) -> bool:
    """Whether the agent has moved on to the final service. Read from the session's
    verification records rather than inferred from a spent trial budget, which
    misses every run that stopped early. An attempt that failed still counts: the
    agent is picking the next trial to verify, not trialing again."""
    return isinstance(session.get("verification"), dict)


_SPARK_BLOCKS = "▁▂▃▄▅▆▇█"


def _format_trial_spark(session: Optional[dict[str, Any]]) -> str:
    """One glyph per trial, scaled from zero: bar heights compare as the
    numbers do, so the size of a gain is visible. A red `·` marks a trial
    that produced no benchmark at all, and a red bar one that measured but
    broke a constraint. Gold marks the best result while no trial meets the
    constraints; green takes over once one does."""
    if not isinstance(session, dict):
        return ""
    trials = session.get("trials")
    series = trials.get("series") if isinstance(trials, dict) else None
    if not isinstance(series, list) or not series:
        return ""
    failed = trials.get("failed")
    if not isinstance(failed, list) or len(failed) != len(series):
        failed = [False] * len(series)
    values = [v for v in series if isinstance(v, (int, float))]
    if not values:
        return "·" * len(series)
    high = max(values)
    passed = [v for v, f in zip(series, failed) if isinstance(v, (int, float)) and not f]
    # The best trial is the answer the run found; everything else is context. Gold
    # is that answer while none meets the constraints, so it gives way to green as
    # soon as one does.
    best = max(passed) if passed else max(values)
    out = []
    for value, is_failed in zip(series, failed):
        if not isinstance(value, (int, float)):
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


def _format_trial_progress(session: Optional[dict[str, Any]], *, in_flight: bool = False) -> str:
    """The ` (N/M)` suffix; stays outside the status markup to render in the
    default color. While trialing, `N` is the trial being worked on rather than
    the completed count, so `trialing (2/3)` cannot read as two finished."""
    if not isinstance(session, dict):
        return ""
    trials = session.get("trials")
    trials_num = session.get("trials_num")
    if not isinstance(trials, dict) or not (trials.get("count") or isinstance(trials_num, int)):
        return ""
    count = trials.get("count") or 0
    if in_flight:
        count = min(count + 1, trials_num) if isinstance(trials_num, int) else count + 1
    progress = str(count)
    if isinstance(trials_num, int):
        progress += f"/{trials_num}"
    return f" [secondary]({progress})[/]"


def print_presets(
    presets: list[Preset],
    sessions: Optional[list[dict[str, Any]]] = None,
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
    presets: list[Preset],
    sessions: Optional[list[dict[str, Any]]] = None,
    verbose: bool = False,
    all_presets: bool = False,
    limit: Optional[int] = None,
) -> Table:
    table = Table(box=None)
    table.add_column("ID", no_wrap=True)
    table.add_column("BASE", no_wrap=True, style="secondary")
    table.add_column("RESOURCES" if verbose else "GPU", style="secondary")
    # CONSTRAINTS is the test that was asked for; BENCHMARK is the best trial under it.
    table.add_column("CONSTRAINTS", no_wrap=True)
    table.add_column("BENCHMARK", min_width=len("tps=1"), overflow="fold")
    # The search shape, one glyph per trial. Unlabelled: it reads on sight.
    table.add_column("", no_wrap=True)
    table.add_column("STATUS", no_wrap=True)
    table.add_column("SUBMITTED", no_wrap=True, style="secondary")
    if verbose:
        table.add_column("NAME", no_wrap=True, style="secondary")
    presets_by_base: dict[str, list[Preset]] = defaultdict(list)
    repo_to_base: dict[str, str] = {}
    for preset in presets:
        presets_by_base[preset.base].append(preset)
        repo_to_base[preset.model] = preset.base
    sessions_by_model: dict[str, list[dict[str, Any]]] = defaultdict(list)
    creations_by_id: dict[str, dict[str, Any]] = {}
    for session in sessions or []:
        if str(session.get("status")) == "success":
            # A completed creation session decorates its preset row.
            creations_by_id[str(session.get("id"))] = session
            continue
        model = str(session.get("model") or "unknown")
        sessions_by_model[repo_to_base.get(model, model)].append(session)

    # One flat list, newest first, as in `dstack ps`. The base is a column, so
    # runs of different models still sort together by when they were submitted.
    # Same contract as `dstack ps`: only active by default, or the single most
    # recent row when nothing is active. `-a` and `-n` show everything.
    rows: list[tuple[str, Any, bool]] = []
    for preset_list in presets_by_base.values():
        rows += [(preset.created_at.isoformat(), preset, True) for preset in preset_list]
    for session_list in sessions_by_model.values():
        rows += [
            (str(session.get("created_at") or ""), session, False) for session in session_list
        ]
    rows.sort(key=lambda r: r[0], reverse=True)
    only_active = not all_presets and limit is None
    if only_active:
        active = [r for r in rows if not r[2] and str(r[1].get("status")) == "running"]
        rows = active or rows[:1]

    for _, item, is_preset in rows[:limit] if limit is not None else rows:
        if is_preset:
            _add_preset(table, item, verbose=verbose, creation=creations_by_id.get(item.id))
        else:
            _add_session(table, item, verbose=verbose)
    return table


def _add_session(table: Table, session: dict[str, Any], *, verbose: bool = False) -> None:
    created = ""
    created_at = session.get("created_at")
    if isinstance(created_at, str):
        try:
            # `Z` is what pydantic v2 emits for UTC, and `datetime.fromisoformat` only
            # accepts it from Python 3.11; dstack supports 3.10.
            created = pretty_date(datetime.fromisoformat(created_at.replace("Z", "+00:00")))
        except ValueError:
            created = created_at
    benchmark = ""
    gpu = ""
    status_key = str(session.get("status", ""))
    if status_key == "running" and _verifying(session):
        status_key = "verifying"
    status = _format_status(status_key) + _format_trial_progress(
        session, in_flight=status_key == "running"
    )
    trials = session.get("trials")
    best = trials.get("best") if isinstance(trials, dict) else None
    # Nothing passed: fall back to the fastest attempt that did not.
    breached = not isinstance(best, dict)
    if breached and isinstance(trials, dict):
        best = trials.get("best_failed")
    if isinstance(best, dict):
        gpu = best.get("gpu") or ""
    if not gpu and isinstance(trials, dict):
        # Trials can record hardware without ever producing a benchmark.
        gpu = trials.get("gpu") or ""
    constraints = session.get("constraints") or {}
    parts = []
    objective = []
    if constraints.get("input_tokens") and constraints.get("output_tokens"):
        objective.append(
            f"io={_format_token_count(constraints['input_tokens'])}"
            f"/{_format_token_count(constraints['output_tokens'])}"
        )
    # Shown even at `0%`: rows are only comparable when it matches.
    input_tokens = constraints.get("input_tokens")
    if input_tokens:
        shared_prefix_tokens = constraints.get("shared_prefix_tokens") or 0
        share = round(100 * shared_prefix_tokens / input_tokens)
        objective.append(f"prefix={share}%")
    concurrency = (best or {}).get("concurrency") or constraints.get("concurrency")
    if concurrency:
        objective.append(f"conc={concurrency}")
    min_context_length = constraints.get("min_context_length")
    if verbose and isinstance(min_context_length, int):
        objective.append(f"ctx>={_format_token_count(min_context_length)}")
    max_ttft = constraints.get("max_ttft")
    if verbose and isinstance(max_ttft, (int, float)):
        objective.append(f"ttft<={_format_duration_ms(max_ttft)}")
    # Stays empty until a trial has produced a benchmark: a run that has measured
    # nothing yet has no best, and `n/a` is noise in a column of numbers.
    if isinstance(best, dict):
        tps = _format_number(best["tok_s"])
        if objective:
            # Per-user leads: aggregate rises with concurrency, so it makes rows at
            # different concurrencies look better or worse than they serve.
            # Same definition as `effective_per_user_tok_per_s`: the steady decode
            # rate, not the aggregate divided by concurrency.
            tpot_ms = best.get("tpot_ms")
            if isinstance(tpot_ms, (int, float)) and tpot_ms > 0:
                parts.append(f"tok/s/user={_format_number(1000 / tpot_ms)}")
            if verbose:
                parts.append(f"tok/s={tps}")
            ttft_ms = best.get("ttft_ms")
            if isinstance(ttft_ms, (int, float)):
                parts.append(f"ttft={_format_duration_ms(ttft_ms)}")
            context_length = best.get("context_length")
            if isinstance(context_length, int):
                parts.append(f"ctx={_format_token_count(context_length)}")
            benchmark = " ".join(parts)
        else:
            benchmark = f"conc={best.get('concurrency')} tps={tps}"
    benchmark = benchmark.strip()
    if benchmark and breached:
        # Marked, not only dimmed: colour alone is not a signal.
        benchmark = f"[secondary]*{benchmark}[/]"
    add_row_from_dict(
        table,
        {
            "ID": str(session.get("id", "")),
            "BASE": str(session.get("model") or ""),
            "NAME": str(session.get("name") or ""),
            "GPU": gpu,
            "RESOURCES": gpu,
            "": _format_trial_spark(session),
            # The constraints are context for the number, so the whole cell recedes;
            # the benchmark beside it is what the reader came for and stays bright.
            "CONSTRAINTS": f"[secondary]{' '.join(objective)}[/]" if objective else "",
            "BENCHMARK": benchmark,
            "STATUS": status,
            "SUBMITTED": created,
        },
    )


def _add_preset(
    table: Table,
    preset: Preset,
    *,
    verbose: bool,
    creation: Optional[dict[str, Any]] = None,
) -> None:
    groups = preset.service.replica_groups
    column = "RESOURCES" if verbose else "GPU"
    row = {
        "ID": preset.id,
        "NAME": preset.name or "",
        column: _format_resources(groups[0].resources, verbose=verbose),
        "BASE": preset.base,
        "STATUS": _format_status("ready") + _format_trial_progress(creation),
        "": _format_trial_spark(creation),
        "CONSTRAINTS": format_preset_objective(
            preset,
            # The preset carries what it was asked for; the creation record is the
            # fallback for presets saved before it did.
            min_context_length=preset.min_context_length
            or (creation or {}).get("constraints", {}).get("min_context_length"),
            max_ttft=preset.max_ttft or (creation or {}).get("constraints", {}).get("max_ttft"),
            verbose=verbose,
        ),
        "BENCHMARK": format_preset_benchmark(preset, verbose=verbose),
        "SUBMITTED": pretty_date(preset.created_at),
    }
    if verbose and preset.model != preset.base:
        row["BASE"] = f"[secondary]  repo={preset.model}[/]"
    add_row_from_dict(table, row)
    if len(groups) > 1:
        for group in groups:
            add_row_from_dict(
                table,
                {
                    "BASE": f"  group={group.name}",
                    column: _format_resources(group.resources, verbose=verbose),
                },
                style="secondary",
            )


def format_preset_objective(
    preset: Preset,
    *,
    min_context_length: Optional[int] = None,
    max_ttft: Optional[float] = None,
    verbose: bool = False,
) -> str:
    """What was asked for. The context the configuration actually reached is a
    result and sits next to the numbers; the context that was *required* is shown
    here under `-v`. Two runs can share every constraint and still serve different
    context lengths, so both are worth seeing."""
    workload = preset.validations[0].benchmark.workload
    parts = [
        f"io={_format_token_count(workload.input_tokens)}"
        f"/{_format_token_count(workload.output_tokens)}",
    ]
    share = round(100 * workload.shared_prefix_tokens / workload.input_tokens)
    parts.append(f"prefix={share}%")
    parts.append(f"conc={workload.concurrency}")
    # Absent for presets saved before the creation record was consulted.
    if verbose and min_context_length is not None:
        parts.append(f"ctx>={_format_token_count(min_context_length)}")
    # The latency ceiling only explains a number that is near it, so it waits for `-v`.
    if verbose and max_ttft is not None:
        parts.append(f"ttft<={_format_duration_ms(max_ttft)}")
    # Context for the number, so the whole cell recedes.
    return f"[secondary]{' '.join(parts)}[/]"


def _breaches_constraints(preset: Preset) -> bool:
    """Whether the verified benchmark misses what was asked for. A session that
    found no compliant trial verifies its best failed one, so a preset can be
    real, reproducible, and still fall short."""
    metrics = preset.validations[0].benchmark.metrics
    if preset.max_ttft is not None and metrics.ttft_ms.p50 > preset.max_ttft:
        return True
    return preset.min_context_length is not None and (
        preset.context_length < preset.min_context_length
    )


def format_preset_benchmark(preset: Preset, *, verbose: bool = False) -> str:
    benchmark = preset.validations[0].benchmark
    metrics = benchmark.metrics
    # The workload and context define the number, so they are always shown next
    # to it: two presets are comparable only when all three match.
    parts = [
        f"tok/s/user={_format_number(benchmark.effective_per_user_tok_per_s)}",
    ]
    if verbose:
        parts.append(f"tok/s={_format_number(benchmark.effective_output_tok_per_s)}")
    parts += [
        f"ttft={_format_duration_ms(metrics.ttft_ms.p50)}",
        f"ctx={_format_token_count(preset.context_length)}",
    ]
    text = " ".join(parts)
    if _breaches_constraints(preset):
        # Marked, not only dimmed: colour alone is not a signal. Same `*` a
        # session row uses when it has nothing but failed trials to show.
        return f"[secondary]*{text}[/]"
    return text


def _format_duration_ms(value: float) -> str:
    """Milliseconds below a second, seconds above it. A bare `4152` reads as small
    until you notice the unit; `4.15s` does not."""
    # 999.6 rounds to 1000, which must read as 1s rather than 1000ms.
    if value < 999.5:
        return f"{_format_number(value)}ms"
    return f"{_format_number(value / 1000)}s"


def _format_token_count(value: int) -> str:
    for divisor, suffix in ((1024 * 1024, "M"), (1024, "K")):
        if value >= divisor and value % divisor == 0:
            return f"{value // divisor}{suffix}"
    return str(value)


def _format_number(value: float) -> str:
    # `g` switches to scientific notation for values >= 1000 (after rounding).
    if abs(value) >= 999.5:
        return f"{value:.0f}"
    return f"{value:.3g}"


def _format_latency(value_ms: float) -> str:
    if value_ms >= 1000:
        return f"{_format_number(value_ms / 1000)}s"
    return f"{_format_number(value_ms)}ms"


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
