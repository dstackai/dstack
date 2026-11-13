from typing import Any, Dict, List, Optional

import pytest
from pydantic import ValidationError

from dstack._internal.core.models.presets import (
    PresetBenchmark,
    validate_preset_file_path,
    validate_preset_file_paths,
)


def get_benchmark_data(workload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "tool": "vllm bench serve",
        "tool_version": "0.11.0",
        "command": "vllm bench serve --base-url $SERVICE_URL",
        "workload": workload,
        "metrics": {
            "successful_requests": 16,
            "failed_requests": 0,
            "duration_seconds": 48.64,
            "total_input_tokens": 16384,
            "total_output_tokens": 2048,
            "output_tok_per_s": 42.1,
            "per_user_tok_per_s": 42.1,
            "ttft_ms": {"mean": 110.9, "p50": 108.2, "p99": 121.6},
            "tpot_ms": {"mean": 7.5, "p50": 7.4, "p99": 8.1},
        },
    }


def get_workload_data(**overrides: Any) -> Dict[str, Any]:
    workload: Dict[str, Any] = {
        "api": "chat_completions",
        "num_requests": 16,
        "input_tokens": 1024,
        "output_tokens": 128,
        "concurrency": 1,
    }
    workload.update(overrides)
    return workload


class TestValidatePresetFilePaths:
    """The single owner of the preset file rules: push (client and server) and
    pull all go through it, so every rule is pinned here once."""

    @pytest.mark.parametrize(
        ("paths", "error"),
        [
            # Per-path rules.
            pytest.param([""], "must be a relative POSIX path", id="empty-path"),
            pytest.param(["/etc/passwd"], "must be a relative POSIX path", id="absolute"),
            pytest.param(["patch\\a.txt"], "must be a relative POSIX path", id="backslash"),
            # `:` covers Windows drive letters and is invalid on Windows targets.
            pytest.param(["c:a.txt"], "must be a relative POSIX path", id="colon"),
            pytest.param(["../a.txt"], "must be a relative POSIX path", id="leading-parent"),
            pytest.param(["patch/../a.txt"], "must be a relative POSIX path", id="inner-parent"),
            pytest.param(["./a.txt"], "must be a relative POSIX path", id="leading-current"),
            pytest.param(["patch/./a.txt"], "must be a relative POSIX path", id="inner-current"),
            pytest.param(["patch//a.txt"], "must be a relative POSIX path", id="empty-segment"),
            pytest.param(["patch/"], "must be a relative POSIX path", id="trailing-slash"),
            # The local store keeps the preset document at this path.
            pytest.param(["preset.yml"], "the name is reserved", id="reserved"),
            # Whole-list rules.
            pytest.param(
                ["patch/a.txt", "patch/a.txt"],
                "Duplicate preset file path",
                id="duplicate",
            ),
            # `a` and `a/b` cannot both materialize on one filesystem, in either
            # order.
            pytest.param(
                ["patch", "patch/a.txt"],
                "both a file and a directory",
                id="file-before-directory",
            ),
            pytest.param(
                ["patch/a.txt", "patch"],
                "both a file and a directory",
                id="directory-before-file",
            ),
            # Accepted.
            pytest.param([], None, id="accepts-no-files"),
            pytest.param(["a.txt"], None, id="accepts-plain-file"),
            pytest.param(["patch/nested/a.txt"], None, id="accepts-nested-file"),
            pytest.param([".env"], None, id="accepts-dotfile"),
            pytest.param(["patch/a.txt", "patch/b.txt"], None, id="accepts-siblings"),
            # Only the exact reserved path is reserved.
            pytest.param(["preset.yaml", "patch/preset.yml"], None, id="accepts-near-reserved"),
        ],
    )
    def test_applies_every_rule(self, paths: List[str], error: Optional[str]):
        if error is None:
            validate_preset_file_paths(paths)
            for path in paths:
                validate_preset_file_path(path)
            return
        with pytest.raises(ValueError, match=error):
            validate_preset_file_paths(paths)
        if len(paths) == 1:
            # A per-path rule must reject through either entry point, since push
            # checks single paths (`service.files`) and lists (the archives).
            with pytest.raises(ValueError, match=error):
                validate_preset_file_path(paths[0])


class TestPresetBenchmarkWorkload:
    """`api` is a Literal, not a plain string: the agent-facing JSON schema is
    generated from these models. `dataset` states the requested dataset, and its
    absence states that none was — a synthetic workload."""

    def test_rejects_an_unsupported_api(self):
        data = get_benchmark_data(get_workload_data(api="embeddings"))

        with pytest.raises(ValidationError):
            PresetBenchmark.model_validate(data)

    def test_parses_a_dataset_workload(self):
        data = get_benchmark_data(get_workload_data(dataset="sharegpt"))

        benchmark = PresetBenchmark.model_validate(data)

        assert benchmark.workload.dataset == "sharegpt"

    def test_parses_a_workload_without_a_dataset_as_synthetic(self):
        data = get_benchmark_data(get_workload_data())

        benchmark = PresetBenchmark.model_validate(data)

        assert benchmark.workload.dataset is None
        assert benchmark.workload.shared_prefix_tokens == 0

    def test_upgrades_a_stored_synthetic_workload(self):
        # Synthetic workloads used to be stored as the literal `random` next to
        # their shared prefix. The combination can mean nothing else: `random` is
        # rejected as a configuration dataset, and a dataset workload never
        # records a prefix.
        data = get_benchmark_data(get_workload_data(dataset="random", shared_prefix_tokens=768))

        benchmark = PresetBenchmark.model_validate(data)

        assert benchmark.workload.dataset is None
        assert benchmark.workload.shared_prefix_tokens == 768

    def test_keeps_a_dataset_named_random_without_a_prefix(self):
        # Only the legacy combination is rewritten: a dataset workload never
        # carries the prefix key, so one that names `random` stays as written.
        data = get_benchmark_data(get_workload_data(dataset="random"))

        benchmark = PresetBenchmark.model_validate(data)

        assert benchmark.workload.dataset == "random"
