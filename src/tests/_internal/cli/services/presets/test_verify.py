from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from dstack._internal.cli.models.preset_agent import AnyPresetAgentResult
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
from dstack._internal.core.models.envs import EnvSentinel
from dstack._internal.core.models.files import FilePathMapping
from dstack._internal.core.models.presets import PresetConfiguration
from dstack._internal.core.models.profiles import ProfileParams
from tests._internal.cli.common import (
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
            model="community/Qwen3.5-27B-GPTQ-Int4",
            context_length=32768,
            benchmark=get_preset_benchmark(),
            configuration=configuration,
            best_trial=1,
            preset_id="8f3a12c4",
            name=None,
            submitted_at=datetime(2026, 1, 2, 3, 4, tzinfo=timezone.utc),
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
            submitted_at=created_at,
        )

        assert preset.base == "Qwen/Qwen3.5-27B"
        assert preset.model == "community/Qwen3.5-27B-GPTQ-Int4"
        assert preset.context_length == 32768
        assert preset.submitted_at == created_at
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
            submitted_at=datetime(2026, 1, 2, 3, 4, tzinfo=timezone.utc),
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
                submitted_at=datetime(2026, 1, 2, 3, 4, tzinfo=timezone.utc),
            )

    def test_rejects_benchmark_on_a_different_dataset(self, tmp_path):
        run = get_running_service_run()

        # The report's workload defaults to `random`, but the configuration
        # demanded a custom dataset: the benchmark does not match the contract.
        with pytest.raises(CLIError, match="dataset does not match"):
            build_verified_preset(
                run=run,
                preset_configuration=PresetConfiguration(
                    name="qwen-build",
                    base="Qwen/Qwen3.5-27B",
                    dataset="spec_bench",
                ),
                report=get_successful_preset_report(run),
                workspace_path=tmp_path,
                session_path=tmp_path,
                preset_id="ab12cd34",
                name=None,
                submitted_at=datetime(2026, 1, 2, 3, 4, tzinfo=timezone.utc),
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
                submitted_at=datetime(2026, 1, 2, 3, 4, tzinfo=timezone.utc),
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
