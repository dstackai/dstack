from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from dstack._internal.cli.models.endpoint_agent import AgentFinalReport
from dstack._internal.cli.models.endpoints import EndpointConfiguration
from dstack._internal.cli.services.endpoints.agent import (
    EndpointAgentProcessOutput,
    EndpointAgentWorkspace,
)
from dstack._internal.cli.services.endpoints.verify import (
    build_verified_endpoint_preset,
    load_endpoint_agent_report,
)
from dstack._internal.core.errors import CLIError
from dstack._internal.core.models.envs import EnvSentinel
from dstack._internal.core.models.profiles import ProfileParams
from tests._internal.cli.endpoint_presets import (
    get_running_service_run,
    get_successful_endpoint_report,
)

pytestmark = pytest.mark.windows


class TestBuildVerifiedEndpointPreset:
    def test_successful_report_requires_benchmark(self):
        run = get_running_service_run()
        data = get_successful_endpoint_report(run).dict()
        data.pop("benchmark")

        with pytest.raises(ValidationError, match="benchmark"):
            AgentFinalReport.parse_obj(data)

    def test_builds_portable_self_contained_preset(self):
        run = get_running_service_run()
        created_at = datetime(2026, 1, 2, 3, 4, tzinfo=timezone.utc)

        with patch(
            "dstack._internal.cli.services.endpoints.presets.get_current_datetime",
            return_value=created_at,
        ):
            preset = build_verified_endpoint_preset(
                run=run,
                endpoint_configuration=EndpointConfiguration(
                    name="qwen-build",
                    model={"base": "Qwen/Qwen3.5-27B"},
                    context_length=8192,
                    gateway="benchmark-gateway",
                    env=["LICENSE", "TOKENIZERS_PARALLELISM=false"],
                ),
                report=get_successful_endpoint_report(run),
            )

        assert preset.base == "Qwen/Qwen3.5-27B"
        assert preset.model == "community/Qwen3.5-27B-GPTQ-Int4"
        assert preset.context_length == 32768
        assert preset.created_at == created_at
        assert preset.service.name is None
        assert preset.service.gateway is None
        assert all(getattr(preset.service, field) is None for field in ProfileParams.__fields__)
        assert isinstance(preset.service.env["LICENSE"], EnvSentinel)
        assert preset.service.env["TOKENIZERS_PARALLELISM"] == "false"
        assert preset.service.resources.gpu.vendor.value == "nvidia"
        validation = preset.validations[0]
        assert validation.replicas[0].resources[0].gpu.name == ["A6000"]
        assert validation.benchmark.target.type == "server-proxy"
        assert validation.benchmark.client.type == "local"

    def test_rejects_variant_for_exact_model_request(self):
        run = get_running_service_run()
        report = get_successful_endpoint_report(run).copy(update={"model": "other/model"})

        with pytest.raises(CLIError, match="changed an exact model request"):
            build_verified_endpoint_preset(
                run=run,
                endpoint_configuration=EndpointConfiguration(
                    name="qwen-build",
                    model={
                        "repo": "community/Qwen3.5-27B-GPTQ-Int4",
                        "name": "Qwen/Qwen3.5-27B",
                    },
                ),
                report=report,
            )


class TestLoadEndpointAgentReport:
    def _load(self, tmp_path, report_data, redacted_values):
        return load_endpoint_agent_report(
            output=EndpointAgentProcessOutput(report_data=report_data),
            workspace=EndpointAgentWorkspace(path=tmp_path, dstack_home=tmp_path / "home"),
            redacted_values=redacted_values,
        )

    def test_redacts_known_secret_in_benchmark_command_instead_of_failing(self, tmp_path):
        run = get_running_service_run()
        data = get_successful_endpoint_report(run).dict()
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
        data = get_successful_endpoint_report(run).dict()
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
        data = get_successful_endpoint_report(run).dict()
        data["run_id"] = str(data["run_id"])
        data["benchmark"]["command"] = (
            "./benchenv/bin/python bench_service.py --base $DSTACK_SERVER_URL/x"
            " (auth via DSTACK_TOKEN bearer header from env)"
        )

        report = self._load(tmp_path, data, redacted_values=())

        assert report.benchmark is not None
        assert "bearer header" in report.benchmark.command
