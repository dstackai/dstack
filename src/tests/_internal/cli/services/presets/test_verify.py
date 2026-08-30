from datetime import datetime, timezone
from typing import Any

import pytest
from pydantic import ValidationError

from dstack._internal.cli.models.preset_agent import AnyPresetAgentResult, PresetAgentSuccess
from dstack._internal.cli.services.presets.agent import (
    PresetAgentProcessOutput,
)
from dstack._internal.cli.services.presets.build import build_preset
from dstack._internal.cli.services.presets.verify import (
    build_verified_preset,
    load_preset_agent_report,
)
from dstack._internal.cli.services.presets.workspace import (
    PresetAgentWorkspace,
)
from dstack._internal.core.errors import CLIError
from dstack._internal.core.models.common import validate_extra_ignore
from dstack._internal.core.models.configurations import PresetConfiguration
from dstack._internal.core.models.envs import EnvSentinel
from dstack._internal.core.models.files import FilePathMapping
from dstack._internal.core.models.presets import PresetWorkload
from dstack._internal.core.models.profiles import ProfileParams
from dstack._internal.core.models.runs import Run
from tests._internal.cli.common import (
    SHARED_PREFIX_WORKLOAD,
    get_preset,
    get_preset_benchmark,
    get_running_service_run,
    get_successful_preset_report,
)

pytestmark = pytest.mark.windows


class TestBuildVerifiedPreset:
    def test_stores_only_the_creation_contract_not_this_machine_s_deployment(self):
        # `apply` takes name, gateway, env and profile from the user's own
        # configuration, so a shared preset must not carry ours.
        configuration = PresetConfiguration.model_validate(
            {
                "type": "preset",
                "base": "Qwen/Qwen3.5-27B",
                "trials": 3,
                "concurrency": 1,
                "min_context_length": 32768,
                "name": "qwen-build",
                "gateway": "benchmark-gateway",
                "env": {"MY-VAR": "secret", "HF_TOKEN": "hf_secret"},
                "spot_policy": "on-demand",
            }
        )
        base = get_preset()

        preset = build_preset(
            service=base.service,
            verification_replica_groups=base.verified_on,
            base_model="Qwen/Qwen3.5-27B",
            repo="community/Qwen3.5-27B-GPTQ-Int4",
            context_length=32768,
            benchmark=get_preset_benchmark(),
            configuration=configuration,
            best_trial=1,
            preset_id="8f3a12c4",
            name=None,
            created_at=datetime(2026, 1, 2, 3, 4, tzinfo=timezone.utc),
        )

        assert preset.configuration.min_context_length == 32768
        assert preset.configuration.name is None
        assert preset.configuration.gateway is None
        assert not preset.configuration.env
        assert preset.configuration.spot_policy is None
        assert "secret" not in preset.model_dump_json()

    def test_successful_report_requires_benchmark(self):
        run = get_running_service_run()
        data = get_successful_preset_report(run).model_dump()
        data.pop("benchmark")

        with pytest.raises(ValidationError, match="benchmark"):
            validate_extra_ignore(AnyPresetAgentResult, data)

    def test_builds_portable_self_contained_preset(self, tmp_path):
        run = get_running_service_run()
        created_at = datetime(2026, 1, 2, 3, 4, tzinfo=timezone.utc)

        preset = build_verified_preset(
            run=run,
            preset_configuration=PresetConfiguration(
                name="qwen-build",
                base="Qwen/Qwen3.5-27B",
                min_context_length=8192,
                gateway="benchmark-gateway",
                env=["LICENSE", "TOKENIZERS_PARALLELISM=false"],
            ),
            report=get_successful_preset_report(run),
            workspace_path=tmp_path,
            session_path=tmp_path,
            preset_id="ab12cd34",
            name=None,
            created_at=created_at,
        )

        assert preset.base == "Qwen/Qwen3.5-27B"
        assert preset.repo == "community/Qwen3.5-27B-GPTQ-Int4"
        assert preset.context_length == 32768
        assert preset.created_at == created_at
        assert preset.service.name is None
        assert preset.service.gateway is None
        assert all(getattr(preset.service, field) is None for field in ProfileParams.model_fields)
        assert isinstance(preset.service.env["LICENSE"], EnvSentinel)
        assert preset.service.env["TOKENIZERS_PARALLELISM"] == "false"
        assert preset.service.resources.gpu.vendor.value == "nvidia"
        assert preset.verified_on[0].replicas[0].gpu.name == ["A6000"]

    def test_rewrites_file_paths_onto_the_mirrored_session_copies(self, tmp_path):
        # `files` local paths resolve into the agent workspace at submission, and
        # the workspace is deleted when the session ends; the preset must point at
        # the session's mirrored copies, relative to the preset directory so the
        # directory stays portable.
        workspace = tmp_path / "session" / "workspace" / "w"
        (workspace / "service" / "1" / "patches").mkdir(parents=True)
        (workspace / "service" / "1" / "patches" / "moe.py.patch").write_text("--- a\n+++ b\n")
        session = tmp_path / "session"
        (session / "service" / "1" / "patches").mkdir(parents=True)
        (session / "service" / "1" / "patches" / "moe.py.patch").write_text("--- a\n+++ b\n")
        run = get_running_service_run()
        run.run_spec.configuration.files = [
            FilePathMapping(
                local_path=str(workspace / "service" / "1" / "patches"), path="/patches"
            )
        ]

        preset = build_verified_preset(
            run=run,
            preset_configuration=PresetConfiguration(name="qwen-build", base="Qwen/Qwen3.5-27B"),
            report=get_successful_preset_report(run),
            workspace_path=workspace,
            session_path=session,
            preset_id="ab12cd34",
            name=None,
            created_at=datetime(2026, 1, 2, 3, 4, tzinfo=timezone.utc),
        )

        assert preset.service.files[0].local_path == "service/1/patches"
        # The run spec itself is untouched: only the preset copy is re-rooted.
        assert run.run_spec.configuration.files[0].local_path == str(
            workspace / "service" / "1" / "patches"
        )

    def test_rejects_a_file_without_a_mirrored_copy(self, tmp_path):
        workspace = tmp_path / "session" / "workspace" / "w"
        (workspace / "patches").mkdir(parents=True)  # workspace root: not mirrored
        session = tmp_path / "session"
        run = get_running_service_run()
        run.run_spec.configuration.files = [
            FilePathMapping(local_path=str(workspace / "patches"), path="/patches")
        ]

        with pytest.raises(CLIError, match="no mirrored copy"):
            build_verified_preset(
                run=run,
                preset_configuration=PresetConfiguration(
                    name="qwen-build", base="Qwen/Qwen3.5-27B"
                ),
                report=get_successful_preset_report(run),
                workspace_path=workspace,
                session_path=session,
                preset_id="ab12cd34",
                name=None,
                created_at=datetime(2026, 1, 2, 3, 4, tzinfo=timezone.utc),
            )

    def test_verifies_a_shared_prefix_benchmark_named_by_the_benchmark_tool(self, tmp_path):
        # `random` is dstack's own name for a synthetic workload; the report carries
        # the benchmark tool's name for the data it generated, which is
        # `generated-shared-prefix` for SGLang and `random` only for vLLM. Comparing
        # the two rejected a benchmark that answered the request exactly.
        run = get_running_service_run()

        preset = build_verified_preset(
            run=run,
            preset_configuration=_shared_prefix_configuration(),
            report=_shared_prefix_report(run),
            workspace_path=tmp_path,
            session_path=tmp_path,
            preset_id="ab12cd34",
            name=None,
            created_at=datetime(2026, 1, 2, 3, 4, tzinfo=timezone.utc),
        )

        # The stored workload states the request: no dataset was asked for, so
        # none is recorded — the tool's own name for its generated data stays in
        # `command` — while the requested prefix survives into the record.
        assert preset.benchmark.workload.dataset is None
        assert preset.benchmark.workload.shared_prefix_tokens == 130048

    def test_rejects_a_benchmark_without_the_requested_shared_prefix(self, tmp_path):
        run = get_running_service_run()

        with pytest.raises(
            CLIError, match="shared prefix of 0 tokens does not match the requested 130048"
        ):
            build_verified_preset(
                run=run,
                preset_configuration=_shared_prefix_configuration(),
                report=_shared_prefix_report(run, shared_prefix_tokens=0),
                workspace_path=tmp_path,
                session_path=tmp_path,
                preset_id="ab12cd34",
                name=None,
                created_at=datetime(2026, 1, 2, 3, 4, tzinfo=timezone.utc),
            )

    def test_rejects_a_benchmark_at_another_concurrency(self, tmp_path):
        run = get_running_service_run()

        with pytest.raises(
            CLIError, match="concurrency of 8 does not match the requested concurrency of 4"
        ):
            build_verified_preset(
                run=run,
                preset_configuration=_shared_prefix_configuration(),
                report=_shared_prefix_report(run, concurrency=8),
                workspace_path=tmp_path,
                session_path=tmp_path,
                preset_id="ab12cd34",
                name=None,
                created_at=datetime(2026, 1, 2, 3, 4, tzinfo=timezone.utc),
            )

    def test_verifies_a_benchmark_on_the_requested_dataset(self, tmp_path):
        run = get_running_service_run()
        report = _dataset_report(run, dataset="spec_bench")

        preset = build_verified_preset(
            run=run,
            preset_configuration=PresetConfiguration(
                name="qwen-build",
                base="Qwen/Qwen3.5-27B",
                dataset="spec_bench",
            ),
            report=report,
            workspace_path=tmp_path,
            session_path=tmp_path,
            preset_id="ab12cd34",
            name=None,
            created_at=datetime(2026, 1, 2, 3, 4, tzinfo=timezone.utc),
        )

        assert preset.benchmark.workload.dataset == "spec_bench"

    def test_stores_a_dataset_benchmark_without_a_stray_shared_prefix(self, tmp_path):
        # The mirror of the synthetic case: a dataset defines its own requests,
        # so a prefix the report volunteers does not enter the record.
        run = get_running_service_run()

        preset = build_verified_preset(
            run=run,
            preset_configuration=PresetConfiguration(
                name="qwen-build",
                base="Qwen/Qwen3.5-27B",
                min_context_length=8192,
                gateway="benchmark-gateway",
                dataset="spec_bench",
            ),
            report=_dataset_report(run, dataset="spec_bench", shared_prefix_tokens=768),
            workspace_path=tmp_path,
            session_path=tmp_path,
            preset_id="ab12cd34",
            name=None,
            created_at=datetime(2026, 1, 2, 3, 4, tzinfo=timezone.utc),
        )

        assert preset.benchmark.workload.dataset == "spec_bench"
        assert preset.benchmark.workload.shared_prefix_tokens == 0

    # A named dataset is the one dataset name the report and the request share, so
    # the report either echoes it or does not answer the request.
    @pytest.mark.parametrize("reported", ["sharegpt", None])
    def test_rejects_benchmark_on_a_different_dataset(self, tmp_path, reported):
        run = get_running_service_run()

        # Both values are named: "does not match" alone leaves nothing to act on.
        with pytest.raises(
            CLIError,
            match=f"dataset {reported!r} does not match the requested dataset 'spec_bench'",
        ):
            build_verified_preset(
                run=run,
                preset_configuration=PresetConfiguration(
                    name="qwen-build",
                    base="Qwen/Qwen3.5-27B",
                    dataset="spec_bench",
                ),
                report=_dataset_report(run, dataset=reported),
                workspace_path=tmp_path,
                session_path=tmp_path,
                preset_id="ab12cd34",
                name=None,
                created_at=datetime(2026, 1, 2, 3, 4, tzinfo=timezone.utc),
            )

    def test_rejects_variant_for_exact_model_request(self, tmp_path):
        run = get_running_service_run()
        report = get_successful_preset_report(run).model_copy(update={"model": "other/model"})

        with pytest.raises(CLIError, match="changed an exact model request"):
            build_verified_preset(
                run=run,
                preset_configuration=PresetConfiguration(
                    name="qwen-build",
                    model={
                        "repo": "community/Qwen3.5-27B-GPTQ-Int4",
                        "name": "Qwen/Qwen3.5-27B",
                    },
                ),
                report=report,
                workspace_path=tmp_path,
                session_path=tmp_path,
                preset_id="ab12cd34",
                name=None,
                created_at=datetime(2026, 1, 2, 3, 4, tzinfo=timezone.utc),
            )


class TestLoadPresetAgentReport:
    def _load(self, tmp_path, report_data, redacted_values):
        return load_preset_agent_report(
            output=PresetAgentProcessOutput(report_data=report_data),
            workspace=PresetAgentWorkspace(path=tmp_path, dstack_home=tmp_path / "home"),
            redacted_values=redacted_values,
        )

    def test_redacts_known_secret_in_benchmark_command_instead_of_failing(self, tmp_path):
        run = get_running_service_run()
        data = get_successful_preset_report(run).model_dump()
        data["run_id"] = str(data["run_id"])
        data["benchmark"]["command"] = (
            "python bench.py --header 'Authorization: Bearer sk-live-0123456789abcdef'"
        )

        report = self._load(tmp_path, data, redacted_values=("sk-live-0123456789abcdef",))

        assert report.benchmark is not None
        assert report.benchmark.command.endswith("Bearer [redacted]'")
        assert "sk-live" not in report.benchmark.command

    def test_requires_e2e_latency_in_a_fresh_report(self, tmp_path):
        run = get_running_service_run()
        data = get_successful_preset_report(run).model_dump()
        data["run_id"] = str(data["run_id"])
        data["benchmark"]["metrics"].pop("e2e_ms")

        with pytest.raises(CLIError, match="e2e_ms"):
            self._load(tmp_path, data, redacted_values=())

    def test_rejects_a_reported_tpot_that_exceeds_available_slot_time(self, tmp_path):
        run = get_running_service_run()
        data = get_successful_preset_report(run).model_dump()
        data["run_id"] = str(data["run_id"])
        data["benchmark"]["metrics"]["tpot_ms"] = {
            "mean": 137.18,
            "p50": 55.34,
            "p99": 1160.43,
        }

        with pytest.raises(CLIError, match="exceeds the decode time available"):
            self._load(tmp_path, data, redacted_values=())

    def test_still_rejects_unknown_bearer_token(self, tmp_path):
        run = get_running_service_run()
        data = get_successful_preset_report(run).model_dump()
        data["run_id"] = str(data["run_id"])
        data["benchmark"]["command"] = (
            "curl -H 'Authorization: Bearer sk-unknown-9876543210fedcba'"
        )

        with pytest.raises(CLIError, match="bearer token"):
            self._load(tmp_path, data, redacted_values=("some-other-secret-value",))

    def test_allows_bearer_prose_without_credential(self, tmp_path):
        # Regression: "(auth via DSTACK_TOKEN bearer header from env)" failed
        # two live sessions — the word after "bearer" is prose, not a token.
        run = get_running_service_run()
        data = get_successful_preset_report(run).model_dump()
        data["run_id"] = str(data["run_id"])
        data["benchmark"]["command"] = (
            "./benchenv/bin/python bench_service.py --base $DSTACK_SERVER_URL/x"
            " (auth via DSTACK_TOKEN bearer header from env)"
        )

        report = self._load(tmp_path, data, redacted_values=())

        assert report.benchmark is not None
        assert "bearer header" in report.benchmark.command


def _shared_prefix_configuration() -> PresetConfiguration:
    """The configuration from dstackai/dstack#4198: a shared prefix and no dataset."""
    return PresetConfiguration.model_validate(
        {
            "type": "preset",
            "base": "Qwen/Qwen3.5-27B",
            "min_context_length": 262144,
            "max_ttft": 5000,
            "trials": 4,
            "concurrency": 4,
            "input_tokens": 131072,
            "output_tokens": 512,
            "shared_prefix_tokens": 130048,
        }
    )


def _shared_prefix_report(run: Run, **workload: Any) -> PresetAgentSuccess:
    return _report_with_workload(run, {**SHARED_PREFIX_WORKLOAD, **workload})


def _dataset_report(run: Run, **workload: Any) -> PresetAgentSuccess:
    # A dataset defines the request shape, so the workload records what it measured.
    return _report_with_workload(
        run,
        {
            "api": "chat_completions",
            "num_requests": 16,
            "input_tokens": 347,
            "output_tokens": 2451,
            "concurrency": 4,
            **workload,
        },
    )


def _report_with_workload(run: Run, workload: dict[str, Any]) -> PresetAgentSuccess:
    benchmark = get_preset_benchmark()
    benchmark.workload = PresetWorkload.model_validate(workload)
    return get_successful_preset_report(run).model_copy(update={"benchmark": benchmark})
